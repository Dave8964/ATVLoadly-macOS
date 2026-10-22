import hashlib,importlib.util,pathlib,tempfile,unittest,json,subprocess,os
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('publisher',pathlib.Path(__file__).parents[1]/'publish-release.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Publish(unittest.TestCase):
 def test_draft_is_found_without_a_published_git_tag(self):
  draft={'id':42,'tag_name':'macos-v0.7.3-candidate.4','draft':True}
  self.assertEqual(p.find_release([[],[draft]],draft['tag_name']),draft)
  self.assertIsNone(p.find_release([[draft]],'missing'))
 def test_incomplete_or_tampered_draft_is_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);file=root/'app.zip';file.write_bytes(b'verified archive')
   asset={'name':file.name,'size':file.stat().st_size,'digest':'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()}
   self.assertEqual(p.verify_assets(root,[asset]),[file])
   with self.assertRaises(ValueError):p.verify_assets(root,[])
   file.write_bytes(b'tampered archive')
   with self.assertRaises(ValueError):p.verify_assets(root,[asset])
 def test_creation_response_id_drives_upload_and_publish_even_when_listing_is_empty(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);(root/'release-body.md').write_text('notes');(root/'app.zip').write_bytes(b'app')
   tag='macos-v0.7.3-candidate.8';state={'id':42,'tag_name':tag,'draft':True,'prerelease':False,'assets':[]};calls=[]
   def fake_run(command,**kwargs):
    endpoint=command[2];method=command[command.index('--method')+1] if '--method' in command else 'GET';calls.append((method,endpoint))
    if endpoint.endswith('releases?per_page=100'):result=[[]]
    elif endpoint.endswith('/releases') and method=='POST':result=state
    elif endpoint.endswith('/releases/42') and method=='GET':result=state
    elif endpoint.startswith('https://uploads.github.com/'):
     file=pathlib.Path(command[command.index('--input')+1]);result={'id':100+len(state['assets']),'name':file.name,'size':file.stat().st_size,'digest':'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()};state['assets'].append(result)
    elif endpoint.endswith('/releases/42') and method=='PATCH':
     p.verify_assets(root,state['assets']);state.update(draft=False,prerelease=True);result=state
    else:raise AssertionError(command)
    return subprocess.CompletedProcess(command,0,json.dumps(result),'')
   env={'GITHUB_REPOSITORY':'owner/repo','GITHUB_SHA':'a'*40,'QUALIFIED_RELEASES':'false','EXISTING_RELEASE_ID':''}
   with patch.dict(os.environ,env),patch.object(p.sys,'argv',['publisher',tag,str(root)]),patch.object(p.subprocess,'run',side_effect=fake_run):p.main()
   self.assertEqual(sum(endpoint.endswith('releases?per_page=100') for _,endpoint in calls),1)
   self.assertIn(('PATCH','repos/owner/repo/releases/42'),calls)
   self.assertFalse(any('/tags/' in endpoint for _,endpoint in calls))
 def test_existing_published_release_cannot_be_overwritten(self):
  with tempfile.TemporaryDirectory() as temp:
   tag='macos-v0.7.3-candidate.8';release={'id':42,'tag_name':tag,'draft':False}
   env={'GITHUB_REPOSITORY':'owner/repo','GITHUB_SHA':'a'*40,'EXISTING_RELEASE_ID':'42'}
   result=subprocess.CompletedProcess([],0,json.dumps(release),'')
   with patch.dict(os.environ,env),patch.object(p.sys,'argv',['publisher',tag,temp]),patch.object(p.subprocess,'run',return_value=result) as call:
    with self.assertRaises(ValueError):p.main()
    self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()
