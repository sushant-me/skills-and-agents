# IIS Filename Enum (CTF): From Source Disclosure to File Upload RCE 
## TL;DR
This [CTF](https://app.hackinghub.io/hubs/iis-filename-enum) demonstrates how IIS filename enumeration can be abused to uncover archived source code, leading to credential disclosure and full Remote Code Execution (RCE). By enumerating IIS shortnames, sensitive application files were identified and extracted, revealing internal API logic and hardcoded credentials. Chaining this with an insecure file upload and unsafe command execution resulted in complete server compromise.

# Initial Recon
The application had Documentation UI stating the API documentaion's however to keep note that the website i.e ctf.com doesn't by default have IIS runnning by default But a ngnix server. they alreaded provided Shortscan Raw results:
```
Running: Microsoft-IIS/10.0 (ASP.NET v4.0.30319)
Vulnerable: Yes!
════════════════════════════════════════════════════════════════════════════════
REQUIR~1.TXT         REQUIR?.TXT? 
SECRET~1             SECRET?    
USERPA~1.CSV         USERPA?.CSV? 
APICRE~1.CON         APICRE?.CON? 
API202~1.ZIP         API-SO?.ZIP? 
INDEX~1.HTM          INDEX.HTM?          INDEX.HTML
DATABA~1.XML         DATABA?.XML? 
BACKUP~1.SQL         BACKUP?.SQL? 
HIDDEN~1             HIDDEN?    
SECRET~1.TXT         SECRET?.TXT? 
ASPNET~1             ASPNET?             ASPNET_CLIENT
PRIVAT~1             PRIVAT?    
PRIVAT~1.DOC         PRIVAT?.DOC? 
ADMINI~1.ASP         ADMINI?.ASP? 
INTERN~1             INTERN?    
TEMPLA~1             TEMPLA?             TEMPLATES
INTERN~1.XLS         INTERN?.XLS? 
```
Well my attention caught into zip file(API202?.zip) , as the ZIP file contain whole file compressed, but it says API202~.zip we need to fuzz after 202 by looking at this we can either decide it as alphanumerical or just Years so the years must be from 2020-2026 right, By gathering bunch of common keywords and wordlist i used minimal one i.e says 150 lines so our final assumption is that go through each year i.e 2020-2026 then append an keywor from our wordlits (eg: -source, internal, proxy). then i run the ffuf to discover if there any file exists I used the command `ffuf -u ctf.com/api2020FUZZ.zip -w wordlists.txt` then i incremented the number from 2020-2026 then i finally got hit, it was the year 2025 with backup keyword so final url is `https://ctf.com/api2025backup.zip` 

<div style="max-width:900px;margin:28px auto;text-align:center;">
  <img src="images/ffuf.png"
       alt=""
       style="width:100%;max-width:900px;height:auto;display:block;margin:0 auto;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,0.08);background:#f6f6f6;object-fit:contain;"
       loading="lazy" decoding="async" width="1200" height="675">
  <p style="font-size:0.95rem;color:#555;margin-top:8px;line-height:1.35;">
  </p>
</div>

Then i downloaded the Source code via curl with ``curl https://ctf.com/api2025backup.zip -o source-code.zip`` and unziped the file with `unzip source-code.zip`, upon extracting it have some files like README.md, requirements, __MACos. But my attention caught into app.py at first glance it is complete UI then at the beginning of the .py file it was found an hardcoded username and password, then since code is long and i am not code reviewer i parsed the full code to chatgpt. it was explained the entire code and then after some dangling it was found application indeed need `Authorization: Bearer <Token>` then concluded the code actually was base64 of username and password in host format i.e  (**username:password**) then we got the final Token i.e `Authorization: Bearer YXBpX3NlcjpUcnlVcnNlbGYh` using match and replace we got an authenticated access.

# Getting RCE via File Upload 
The initial look at API documentation revealed two crucial endpoint a file upload functionalities(any file), and file converter path, i quickly prepared myself and uploaded a file using this command 
```
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  https://ctf.com/api/files/upload
```
the app returned 
<div style="max-width:900px;margin:28px auto;text-align:center;">
  <img src="images/upload.png"
       alt=""
       style="width:100%;max-width:900px;height:auto;display:block;margin:0 auto;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,0.08);background:#f6f6f6;object-fit:contain;"
       loading="lazy" decoding="async" width="1200" height="675">
  <p style="font-size:0.95rem;color:#555;margin-top:8px;line-height:1.35;">
  </p>
</div>

Then i used the file type convertor API to change the uploaded file format it requires two crucial parameters 1. file_id, 2. output_format, then i request this app with POST request via Burp suite, then it shows an error/debug message stating ``File Converted to <output_format>`` this made me feel the output_format paramter or field is direcrly incorportated into json then i fastly took a look at the source code then found this little pookie sitting there :
```
  # Generate output filename
    base_name = os.path.splitext(filename)[0]
    output_filename = f"{base_name}_converted.{output_format}"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
```
Did you see that field/parameter output_format was directly incorported into OS library without any sanitization and it was user controlled json too, then i quickly crafted an request like this and run simple whoami command by using operators to escape from execution line it was request made with post method:

```
{
"filepath": "&whoami",
"file_id":   "9efa8e33-8d5b-4ed5-9560-7914416461a9",
"output_format":   ";whoami"
}
```
and it returned

<div style="max-width:900px;margin:28px auto;text-align:center;">
  <img src="images/cmd-exec.png"
       alt="Injected email showing malicious form"
       style="width:100%;max-width:900px;height:auto;display:block;margin:0 auto;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,0.08);background:#f6f6f6;object-fit:contain;"
       loading="lazy" decoding="async" width="1200" height="675">
  <p style="font-size:0.95rem;color:#555;margin-top:8px;line-height:1.35;">
  </p>
</div>

did you see that it literally execute the whoami command.
and our main goal is to find flag then i quickly run the ls command there it is flag.txt sitting righ there. and finally it flag was retrieved and challenge solve.

<div style="max-width:900px;margin:28px auto;text-align:center;">
  <img src="images/flag.png"
       alt="Injected email showing malicious form"
       style="width:100%;max-width:900px;height:auto;display:block;margin:0 auto;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,0.08);background:#f6f6f6;object-fit:contain;"
       loading="lazy" decoding="async" width="1200" height="675">
  <p style="font-size:0.95rem;color:#555;margin-top:8px;line-height:1.35;">
    Successfully retrieved the flag
  </p>
</div>

## Conclusion
This CTF provided a real-world learning experience designed by Ben (@nahamsec). It was both insightful and challenging, demonstrating how a seemingly simple IIS misconfiguration can be chained into a high-impact Remote Code Execution (RCE). More importantly, the challenge highlighted the importance of vulnerability chaining—showing how multiple low-severity issues, when combined, can lead to critical security impact.

## Connect With Me

🐦 **X (Twitter)**: @eh_pavan

🌐 **Website**: https://ehpavan.github.io

💻 **GitHub**: https://github.com/ehpavan
