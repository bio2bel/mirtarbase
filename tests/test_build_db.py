# -*- coding: utf-8 -*-

import tempfile
import unittest

from bio2bel_mirtarbase.manager import Manager
from bio2bel_mirtarbase.models import Mirna, Target, Evidence, Interaction


class TestBuildDB(unittest.TestCase):
    def setUp(self):
        """Create temporary file"""

        self.fd, self.path = tempfile.mkstemp()
        self.connection = 'sqlite:///' + self.path

        #create temporary database
        self.manager = Manager(self.connection)
        #fill temporary database
        self.manager.populate()

    def test_populate(self):
        """Test the populate function of the database manager"""

        ev2 = self.manager.session.query(Evidence).filter(Evidence.reference == 18619591).first()
        self.assertEqual("Luciferase reporter assay//qRT-PCR//Western blot//Reporter assay;Microarray", ev2.support)

        mi3 = self.manager.session.query(Evidence).filter(Mirna.id == "MIRT000005").first()
        self.assertEqual("mmu-miR-124-3p", mi3.mir_name)

        targ = self.manager.session.query(Target).filter(Target.entrez_id == 7852).first()
        self.assertEqual("CXCR4", targ.target_gene)

if __name__ == '__main__':
    unittest.main()