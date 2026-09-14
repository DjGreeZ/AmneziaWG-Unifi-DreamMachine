import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
from compatibility import check_system, validate_versions

class CompatibilityTests(unittest.TestCase):
    def test_models_and_newer_versions(self):
        for model in ('UDM.al324', 'UDR.platform', 'UDMPRO.platform', 'UDMSE.platform', 'OTHER.platform'):
            self.assertEqual(validate_versions(model+'.v5.1.33.build', '10.6.101-35991-1'), ('5.1.33','10.6.101'))
        self.assertEqual(validate_versions('6.0.0', '1:11.0.0-1'), ('6.0.0','11.0.0'))
        self.assertEqual(validate_versions('UDR.platform.v5.10.0.build', '10.10.1-1'), ('5.10.0','10.10.1'))
    def test_old_versions_rejected(self):
        for os, network in [('5.1.32','10.6.101'), ('5.1.33','10.6.100'), ('4.99.99','11.0.0')]:
            with self.assertRaises(ValueError):validate_versions(os,network)
    def test_unknown_versions_rejected(self):
        for os, network in [('unknown','10.6.101'), ('5.1.33',''), ('5.1.33','10.6')]:
            with self.assertRaises(ValueError):validate_versions(os,network)
    @patch('compatibility.Path.read_text', return_value='UDR.platform.v5.1.33.build')
    @patch('compatibility.subprocess.run')
    def test_installed_package_fallback(self, run, read):
        run.side_effect=[CompletedProcess([],0,'unknown ok not-installed\t'),CompletedProcess([],0,'install ok installed\t10.6.101-1')]
        self.assertEqual(check_system(),('5.1.33','10.6.101'))
    @patch('compatibility.Path.read_text', return_value='UDM.al324.v5.1.33.build')
    @patch('compatibility.subprocess.run')
    def test_no_installed_network(self, run, read):
        run.return_value=CompletedProcess([],1,'')
        with self.assertRaises(ValueError):check_system()

if __name__ == '__main__':unittest.main()
