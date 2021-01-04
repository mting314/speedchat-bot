import requests
from bs4 import BeautifulSoup

import asyncio
from pyppeteer import launch

# cookies = {'ASP.NET_SessionId': 'dnlbv033ajju0ydsbi4n1hjq', 'iwe_term_enrollment_urn:mace:ucla.edu:ppid:person:63FC23716F3F48459012BA231C11E1BF': '21W', '_shibstate_1609556754_8664': 'https://be.my.ucla.edu/img/audience-nav-bg.jpg', '_shibstate_1609556754_c246': 'https://be.my.ucla.edu/img/blue-divider.gif', '_shibstate_1609556754_b52d': 'https://be.my.ucla.edu/img/header-bg.jpg', '_shibstate_1609556754_547a': 'https://be.my.ucla.edu/img/sprites.png', '_shibstate_1609556754_bf50': 'https://be.my.ucla.edu/img/white-divider.gif', '_shibstate_1609556754_9a16': 'https://be.my.ucla.edu/img/footer-bg.jpg', '_shibstate_1609556802_235f': 'https://be.my.ucla.edu/ClassPlanner/ClassPlan.aspx', 'iwe_term_student_urn:mace:ucla.edu:ppid:person:63FC23716F3F48459012BA231C11E1BF': '21W', 'MyUCLAPortalOptions': 'Spotlight', '_shibstate_1609661386_0166': 'https://be.my.ucla.edu/img/audience-nav-bg.jpg', '_shibstate_1609661386_1827': 'https://be.my.ucla.edu/img/blue-divider.gif', '_shibstate_1609661386_ae3d': 'https://be.my.ucla.edu/img/sprites.png', '_shibstate_1609661386_0236': 'https://be.my.ucla.edu/img/footer-bg.jpg', '_shibstate_1609661386_6c46': 'https://be.my.ucla.edu/img/white-divider.gif', '_shibstate_1609661395_6150': 'https://be.my.ucla.edu/ClassPlanner/ClassPlan.aspx', 'iwe_term_student': '21W', '_shibsession_64656661756c7468747470733a2f2f62652e6d792e75636c612e6564752f73686962626f6c6574682d73702f': '_bfcc19a01482d55bfcaa65e00d330c8b'}
cookies =   {"ASP.NET_SessionId": "dnlbv033ajju0ydsbi4n1hjq","collapsible":"","iwe_term_enrollment_urn:mace:ucla.edu:ppid:person:63FC23716F3F48459012BA231C11E1BF":"21W","_shibstate_1609556754_8664":"https://be.my.ucla.edu/img/audience-nav-bg.jpg","_shibstate_1609556754_c246":"https://be.my.ucla.edu/img/blue-divider.gif","_shibstate_1609556754_b52d":"https://be.my.ucla.edu/img/header-bg.jpg","_shibstate_1609556754_547a":"https://be.my.ucla.edu/img/sprites.png","_shibstate_1609556754_bf50":"https://be.my.ucla.edu/img/white-divider.gif","_shibstate_1609556754_9a16":"https://be.my.ucla.edu/img/footer-bg.jpg","_shibstate_1609556802_235f":"https://be.my.ucla.edu/ClassPlanner/ClassPlan.aspx","iwe_term_student_urn:mace:ucla.edu:ppid:person:63FC23716F3F48459012BA231C11E1BF":"21W","_shibstate_1609661386_0166":"https://be.my.ucla.edu/img/audience-nav-bg.jpg","_shibstate_1609661386_1827":"https://be.my.ucla.edu/img/blue-divider.gif","_shibstate_1609661386_8d32":"https://be.my.ucla.edu/img/header-bg.jpg","_shibstate_1609661386_ae3d":"https://be.my.ucla.edu/img/sprites.png","_shibstate_1609661386_0236":"https://be.my.ucla.edu/img/footer-bg.jpg","_shibstate_1609661386_6c46":"https://be.my.ucla.edu/img/white-divider.gif","_shibstate_1609661395_6150":"https://be.my.ucla.edu/ClassPlanner/ClassPlan.aspx","iwe_term_student":"21W","_shibstate_1609710286_bb66":"https://be.my.ucla.edu/elections/election/logout","_shibstate_1609710286_cb63":"https://be.my.ucla.edu/groupmanager/workgroup/logout","_shibstate_1609710286_fc6b":"https://be.my.ucla.edu/desktop/default/logout","_shibstate_1609710286_3207":"https://be.my.ucla.edu/Classes/default/logout","_shibstate_1609710286_454e":"https://be.my.ucla.edu/apps/default/logout","MyUCLAPortalOptions":"Spotlight","_shibsession_64656661756c7468747470733a2f2f62652e6d792e75636c612e6564752f73686962626f6c6574682d73702f":"_e2c11af9703cfb2c9bdc9e857919d943"}
# cookies = {'iwe_term_enrollment_urn:mace:ucla.edu:ppid:person:63FC23716F3F48459012BA231C11E1BF': '21W', 'iwe_term_student_urn:mace:ucla.edu:ppid:person:63FC23716F3F48459012BA231C11E1BF': '21W', 'iwe_term_student': '21W', '_shibsession_64656661756c7468747470733a2f2f62652e6d792e75636c612e6564752f73686962626f6c6574682d73702f': '_bfcc19a01482d55bfcaa65e00d330c8b'}


headers = {"X-Requested-With": "XMLHttpRequest"}

url = 'https://be.my.ucla.edu/ClassPlanner/ClassSearch.asmx/getTierData'

data = {'search_by_typ_cd':'classidnumber','term_cd':'21W','ses_grp_cd':'%','subj_area_cd':'JAPAN  ','crs_catlg_no':'0005    ','class_no':'%','class_id':'261015200','class_units':'%','instr_nm':'%','act_enrl_seq_num':'%','active_enrl_fl':'y','class_prim_act_fl':'y','id':'XQoZ42DDTYVlvhM/J2rtrYBBxdvDDH/ISsmqXiWi5NE=','searchKey':'4c8bc22d8c72c55625198fb8f94ccf14'}
browser = await launch()



await page.type('#username', 'username')
await page.type('#password', 'password')
await page.click('#login')
await page.waitForNavigation()

r = requests.post(url, data=data,  headers=headers, cookies=cookies)

soup = BeautifulSoup(r.content, "lxml")
print(soup)