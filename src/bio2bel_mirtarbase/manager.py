# -*- coding: utf-8 -*-

"""Manager for Bio2BEL miRTarBase."""

import logging
import time

from bio2bel import AbstractManager
from bio2bel.manager.bel_manager import BELManagerMixin
from bio2bel.manager.flask_manager import FlaskMixin
import bio2bel_entrez
from bio2bel_entrez.manager import VALID_ENTREZ_NAMESPACES
import bio2bel_hgnc
from pybel import BELGraph
from pybel.constants import DIRECTLY_DECREASES, FUNCTION, IDENTIFIER, MIRNA, NAME, NAMESPACE, RNA
from tqdm import tqdm

from .constants import MODULE_NAME
from .models import Base, Evidence, Interaction, MIRBASE, Mirna, Species, Target
from .parser import get_data

log = logging.getLogger(__name__)


def _build_entrez_map(hgnc_manager):
    """Build a mapping from entrez gene identifiers to their database models from :py:mod:`bio2bel_hgnc.models`.

    :param Optional[str] hgnc_connection:
    :rtype: dict[str,bio2bel_hgnc.models.HGNC]
    """
    log.info('getting entrez mapping')

    t = time.time()
    emap = {
        model.entrez: model
        for model in hgnc_manager.hgnc()
        if model.entrez
    }
    log.info('got entrez mapping in %.2f seconds', time.time() - t)
    return emap


def _get_name(data):
    if NAME in data:
        return data[NAME]
    elif IDENTIFIER in data:
        return data[IDENTIFIER]


class Manager(AbstractManager, BELManagerMixin, FlaskMixin):
    """Manages the mirTarBase database."""

    module_name = MODULE_NAME
    flask_admin_models = [Mirna, Target, Species, Interaction, Evidence]

    @property
    def _base(self):
        return Base

    def is_populated(self):
        """Check if the database is already populated.

        :rtype: bool
        """
        return 0 < self.count_mirnas()

    def populate(self, source=None, update_hgnc=False):
        """Populate database with the data from miRTarBase.

        :param str source: path or link to data source needed for :func:`get_data`
        :param bool update_hgnc: Should HGNC be updated?
        """
        hgnc_manager = bio2bel_hgnc.Manager(connection=self.connection)

        if not hgnc_manager.is_populated() or update_hgnc:
            hgnc_manager.populate()

        t = time.time()
        log.info('getting data')
        df = get_data(source)
        log.info('got data in %.2f seconds', time.time() - t)

        name_mirna = {}
        target_set = {}
        species_set = {}
        interaction_set = {}

        emap = _build_entrez_map(hgnc_manager)

        log.info('building models')
        t = time.time()
        for (index, mirtarbase_id, mirna_name, mirna_species, gene_name, entrez_id, target_species, exp, sup_type,
             pubmed) in tqdm(df.itertuples(), total=len(df.index)):
            # create new miRNA instance

            entrez_id = str(int(entrez_id))

            interaction_key = (mirna_name, entrez_id)
            interaction = interaction_set.get(interaction_key)

            if interaction is None:
                mirna = name_mirna.get(mirna_name)

                if mirna is None:
                    species = species_set.get(mirna_species)

                    if species is None:
                        species = species_set[mirna_species] = Species(name=mirna_species)
                        self.session.add(species)

                    mirna = name_mirna[mirna_name] = Mirna(
                        name=mirna_name,
                        species=species
                    )
                    self.session.add(mirna)

                target = target_set.get(entrez_id)
                if target is None:
                    species = species_set.get(target_species)

                    if species is None:
                        species = species_set[target_species] = Species(name=target_species)
                        self.session.add(species)

                    target = target_set[entrez_id] = Target(
                        entrez_id=entrez_id,
                        species=species,
                        name=gene_name,
                    )

                    if entrez_id in emap:
                        g_first = emap[entrez_id]
                        target.hgnc_symbol = g_first.symbol
                        target.hgnc_id = str(g_first.identifier)

                    self.session.add(target)

                # create new interaction instance
                interaction = interaction_set[interaction_key] = Interaction(
                    mirtarbase_id=mirtarbase_id,
                    mirna=mirna,
                    target=target
                )
                self.session.add(interaction)

            # create new evidence instance
            new_evidence = Evidence(
                experiment=exp,
                support=sup_type,
                reference=pubmed,
                interaction=interaction,
            )
            self.session.add(new_evidence)

        log.info('built models in %.2f seconds', time.time() - t)

        log.info('committing models')
        t = time.time()
        self.session.commit()
        log.info('committed after %.2f seconds', time.time() - t)

    def count_targets(self):
        """Count the number of targets in the database.

        :rtype: int
        """
        return self._count_model(Target)

    def count_mirnas(self):
        """Count the number of miRNAs in the database.

        :rtype: int
        """
        return self._count_model(Mirna)

    def count_interactions(self):
        """Count the number of interactions in the database.

        :rtype: int
        """
        return self._count_model(Interaction)

    def count_evidences(self):
        """Count the number of evidences in the database.

        :rtype: int
        """
        return self._count_model(Evidence)

    def list_evidences(self):
        """List the evidences in the database.

        :rtype: list[Evidence]
        """
        return self._list_model(Evidence)

    def count_species(self):
        """Count the number of species in the database.

        :rtype: int
        """
        return self._count_model(Species)

    def summarize(self):
        """Return a summary dictionary over the content of the database.

        :rtype: dict[str,int]
        """
        return dict(
            targets=self.count_targets(),
            mirnas=self.count_mirnas(),
            species=self.count_species(),
            interactions=self.count_interactions(),
            evidences=self.count_evidences(),
        )

    def query_mirna_by_mirtarbase_identifier(self, mirtarbase_id):
        """Get an miRNA by the miRTarBase interaction identifier.

        :param str mirtarbase_id: An miRTarBase interaction identifier
        :rtype: Optional[Mirna]
        """
        interaction = self.session.query(Interaction).filter(Interaction.mirtarbase_id == mirtarbase_id).one_or_none()

        if interaction is None:
            return

        return interaction.mirna

    def query_mirna_by_mirtarbase_name(self, name):
        """Get an miRNA by its miRTarBase name.

        :param str name: An miRTarBase name
        :rtype: Optional[Mirna]
        """
        return self.session.query(Mirna).filter(Mirna.name == name).one_or_none()

    def query_mirna_by_hgnc_identifier(self, hgnc_id):
        """Query for a miRNA by its HGNC identifier.

        :param str hgnc_id: HGNC gene identifier
        :rtype: Optional[Mirna]
        """
        raise NotImplementedError

    def query_mirna_by_hgnc_symbol(self, hgnc_symbol):
        """Query for a miRNA by its HGNC gene symbol.

        :param str hgnc_symbol: HGNC gene symbol
        :rtype: Optional[Mirna]
        """
        raise NotImplementedError

    def query_target_by_entrez_id(self, entrez_id):
        """Query for one target.

        :param str entrez_id: Entrez gene identifier
        :rtype: Optional[Target]
        """
        return self.session.query(Target).filter(Target.entrez_id == entrez_id).one_or_none()

    def query_target_by_hgnc_symbol(self, hgnc_symbol):
        """Query for one target.

        :param str hgnc_symbol: HGNC gene symbol
        :rtype: Optional[Target]
        """
        return self.session.query(Target).filter(Target.hgnc_symbol == hgnc_symbol).one_or_none()

    def query_target_by_hgnc_identifier(self, hgnc_id):
        """Query for one target.

        :param str hgnc_id: HGNC gene identifier
        :rtype: Optional[Target]
        """
        return self.session.query(Target).filter(Target.hgnc_id == hgnc_id).one_or_none()

    def _enrich_rna_handle_hgnc(self, identifier, name):
        if identifier:
            return self.query_target_by_hgnc_identifier(identifier)
        if name:
            return self.query_target_by_hgnc_symbol(name)
        raise IndexError

    def _enrich_rna_handle_entrez(self, identifier, name):
        if identifier:
            return self.query_target_by_entrez_id(identifier)
        if name:
            return self.query_target_by_entrez_id(name)
        raise IndexError

    def enrich_rnas(self, graph):
        """Add all of the miRNA inhibitors of the RNA nodes in the graph.

        :param pybel.BELGraph graph: A BEL graph
        """
        log.debug('enriching inhibitors of RNA')
        count = 0

        for node, data in graph.nodes(data=True):
            if data[FUNCTION] != RNA:
                continue

            if NAMESPACE not in data:
                continue

            namespace = data[NAMESPACE]
            identifier = data.get(IDENTIFIER)
            name = data.get(NAME)

            if namespace.lower() == 'hgnc':
                target = self._enrich_rna_handle_hgnc(identifier, name)
            elif namespace.lower() in VALID_ENTREZ_NAMESPACES:
                target = self._enrich_rna_handle_entrez(identifier, name)
            else:
                log.warning("Unable to map namespace: %s", namespace)
                continue

            if target is None:
                log.warning("Unable to find RNA: %s:%s", namespace, _get_name(data))
                continue

            for interaction in target.interactions:
                for evidence in interaction.evidences:
                    count += 1
                    graph.add_qualified_edge(
                        interaction.mirna.as_bel(),
                        node,
                        relation=DIRECTLY_DECREASES,
                        evidence=evidence.support,
                        citation=str(evidence.reference),
                        annotations={
                            'Experiment': evidence.experiment,
                            'SupportType': evidence.support,
                        }
                    )

        log.debug('added %d MTIs', count)

    def enrich_mirnas(self, graph):
        """Add all target RNAs to the miRNA nodes in the graph.

        :param pybel.BELGraph graph: A BEL graph
        """
        log.debug('enriching miRNA targets')
        count = 0

        mirtarbase_names = set()

        for node, data in graph.nodes(data=True):
            if data[FUNCTION] != MIRNA or NAMESPACE not in data:
                continue

            namespace = data[NAMESPACE]

            if namespace.lower() == 'mirtarbase':
                if NAME in data:
                    mirtarbase_names.add(data[NAME])
                raise IndexError('no usable identifier for {}'.format(data))

            elif namespace.lower() in {'mirbase', 'hgnc'} | VALID_ENTREZ_NAMESPACES:
                log.debug('not yet able to map %s', namespace)
                continue

            else:
                log.debug("unable to map namespace: %s", namespace)
                continue

        if not mirtarbase_names:
            log.debug('no mirnas found')
            return

        query = self.session \
            .query(Mirna, Interaction, Evidence) \
            .join(Interaction) \
            .join(Evidence) \
            .filter(Mirna.filter_name_in(mirtarbase_names))

        for mirna, interaction, evidence in query:
            count += 1
            evidence.add_to_graph(graph)

        log.debug('added %d MTIs', count)

    def to_bel(self):
        """Serialize miRNA-target interactions to BEL.

        :rtype: pybel.BELGraph
        """
        graph = BELGraph(
            name='miRTarBase',
            version='1.0.0',
        )

        hgnc_manager = bio2bel_hgnc.Manager(engine=self.engine, session=self.session)
        hgnc_namespace = hgnc_manager.upload_bel_namespace()
        graph.namespace_url[hgnc_namespace.keyword] = hgnc_namespace.url

        entrez_manager = bio2bel_entrez.Manager(engine=self.engine, session=self.session)
        entrez_namespace = entrez_manager.upload_bel_namespace()
        graph.namespace_url[entrez_namespace.keyword] = entrez_namespace.url

        graph.namespace_pattern[MIRBASE] = '^.*$'

        # TODO check if entrez has all species uploaded and optionally populate remaining species
        # TODO look up miRNA by miRBase

        for evidence in tqdm(self.list_evidences(), total=self.count_evidences(),
                             desc='Mapping miRNA-target interactions to BEL'):
            evidence.add_to_graph(graph)

        return graph
