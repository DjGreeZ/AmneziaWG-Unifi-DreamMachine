import tempfile
from pathlib import Path
from unittest.mock import Mock
with tempfile.TemporaryDirectory() as d:
 ns={'__name__':'test'}
 exec(Path(__file__).with_name('service.py').read_text().replace("ROOT=Path('/data/awg-native')",'ROOT=Path('+repr(d)+')'),ns)
 Path(d,'active.conf').write_text('test-config')
 for name in ('bridge','stop_engine','ensure_bridge','start_engine'):ns[name]=Mock()
 ns['native_enabled']=Mock(return_value=(False,True));ns['engine_alive']=Mock(return_value=True)
 ns['lifecycle_tick']();ns['stop_engine'].assert_called_once();assert ns['STATE']['phase']=='disabled'
 ns['native_enabled'].return_value=(False,False);ns['lifecycle_tick']();assert ns['STATE']['phase']=='unbound'
 ns['native_enabled'].return_value=(True,True);ns['engine_alive'].return_value=False;ns['probe']=Mock(return_value=('203.0.113.1',1))
 ns['lifecycle_tick']();ns['start_engine'].assert_called_once_with('test-config');assert ns['STATE']['phase']=='active'
 ns['JOB'].acquire();ns['native_enabled'].reset_mock();ns['lifecycle_tick']();ns['native_enabled'].assert_not_called();ns['JOB'].release()
 print('Disable, delete, re-enable and upload synchronization passed.')
