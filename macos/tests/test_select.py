import json,os,pathlib,subprocess,sys,tempfile,unittest
class Selection(unittest.TestCase):
 def test_unchanged_inputs_skip_and_qualification_requires_stable_release(self):
  root=pathlib.Path(__file__).resolve().parents[2]
  with tempfile.TemporaryDirectory() as temp:
   folder=pathlib.Path(temp);upstream=folder/'upstream.json';published=folder/'published.json';output=folder/'output';notes=folder/'notes'
   upstream.write_text(json.dumps([[{'tag_name':'v0.7.3','body':'Official release notes'}]]));published.write_text('[[]]')
   env=dict(os.environ,GITHUB_SHA='test-source-commit',GITHUB_RUN_NUMBER='2',GITHUB_OUTPUT=str(output),QUALIFIED_RELEASES='false')
   def run():
    output.write_text('')
    subprocess.run([sys.executable,str(root/'macos/select-release.py'),str(upstream),str(published),str(notes)],env=env,cwd=root,check=True,capture_output=True)
    return output.read_text()
   self.assertIn('changed=true',run())
   published.write_text(json.dumps([[{'draft':False,'prerelease':True,'body':notes.read_text()}]]))
   self.assertIn('changed=false',run())
   env['QUALIFIED_RELEASES']='true'
   self.assertIn('changed=true',run())
if __name__=='__main__':unittest.main()
