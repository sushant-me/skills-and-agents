Title: Access All Areas Write-Up (NahamCon-CTF-2025)

URL Source: https://medium.com/@kianoosh.9944/access-all-areas-write-up-nahamcon-ctf-2025-2c8b400942b4

Published Time: 2025-05-28T14:37:57Z

Markdown Content:
[![Image 1: Kianoush](https://miro.medium.com/v2/resize:fill:32:32/1*tiNTHEvxromx3KgMPBFERg.png)](https://medium.com/@kianoosh.9944?source=post_page---byline--2c8b400942b4-----------------------------------------)

6 min read

May 28, 2025

--

--

## Introduction

In this write-up, I share how I initially chased a command injection hypothesis wrongfully and hit a dead end.   
After the solution was revealed, I dug deeper, researched the exploit, and uncovered a clear LFI + Server-Side XSS (SSXSS)!!! via headless Chrome PDF rendering that resides on the server side, not client's one!  
Learn how key clues like timestamp formats and PDF metadata can guide you from a wrong assumption to a successful exploit and enjoy =)

## Initial Mistake

At first, I thought the threat model for this challenge was about **Command Injection** leading to RCE, because of its name, “Access All Areas”.

As a result, I found an endpoint called (`/api/update.php`) and when looked at my burp logs that was sending JSON data periodically from a JavaScript code residing on the home page path, taking two parameters: `control` and `value`. I assumed these might be vulnerable to command injection.

Here, I incorrectly assumed the threat model involved command injection potentially leading to Remote Code Execution (RCE). Another indicator was that each log entry included a timestamp formatted similarly to PHP’s standard date output. (`php -r "echo date('d/m/Y H:i:s');"`).

Press enter or click to view image in full size

![Image 2](https://miro.medium.com/v2/resize:fit:700/1*BAhsQAlxpD-X5Jn--lLmNg.png)

Realized the timing and format are exactly similar!

## Failed Attempts

I believed the `control` parameter might be vulnerable because the `value` parameter only accepted integers, limiting how it could be attacked.

I tested various special characters (`;`, `|`, `<`, `&`) but always received HTTP 400 errors, indicating strict sanitization. I found that sending an array value like `{"control": ["test"]}` resulted in the word "Array" appearing in the PDF instead of the word “test”. However, attempts to exploit this failed completely.

Press enter or click to view image in full size

![Image 3](https://miro.medium.com/v2/resize:fit:700/1*AYfLhj4WvmdWOqyBEli3ow.png)

Posting a random value for the parameter “control” to the /api/update.php

Press enter or click to view image in full size

![Image 4](https://miro.medium.com/v2/resize:fit:700/1*--Gn9o16Jo72rsxLRAlpVw.png)

Once refreshed the log page, I could see it is now printed there!

***

Press enter or click to view image in full size

![Image 5](https://miro.medium.com/v2/resize:fit:700/1*V3d6B7iRlE3cUebXgWJlCQ.png)

Accidentally sent an array format vlaue and that got accepted.

Press enter or click to view image in full size

![Image 6](https://miro.medium.com/v2/resize:fit:700/1*S-6MOc1xa3hAlFNkgfGvGg.png)

I did input [“test”] but it is showing me Array! not “test”

I also noticed something odd about the PDF — it had a `.html` extension but was clearly a PDF file. Checking the PDF properties, I saw an unfamiliar name (`Skia/PDF`), but initially, I didn't understand its importance.

Press enter or click to view image in full size

![Image 7](https://miro.medium.com/v2/resize:fit:700/1*Z-QV5e9pYohW2JJTfostcQ.png)

Weird PDF! file, end with .html and producer is not adobe!

## Finding the LFI (What I did, and what I Should Have Done)

Looking back, I missed a clear sign: the `log` parameter with the `.log` extension hinted strongly at a **Local File Inclusion (LFI)** or **Path Traversal** vulnerability. Initially, I suspected it and tried accessing `../../../etc/passwd` and gave up too quickly when that failed, and that was my biggest mistake :(

Instead, I should have:

*   Used a common LFI list from SecLists ([LFI-gracefulsecurity-linux.txt](https://github.com/danielmiessler/SecLists/blob/master/Fuzzing/LFI/LFI-gracefulsecurity-linux.txt)) → if you wonder how could I possibly knew that, the answer is: this worlist had more Linux and more nginx related paths, and that I could only knew if I fingerprinted the website, like by the help of wappalyzer! and if I was focuing more on the backend tech — > big lesseon (KNOW YOUR TARGET)
*   Added traversal (`../../../`) to begining of the wordlist easily by using `awk '{print "../../../"$0}'`[LFI-gracefulsecurity-linux.txt](https://github.com/danielmiessler/SecLists/blob/master/Fuzzing/LFI/LFI-gracefulsecurity-linux.txt)`> lfi-ready`[.txt](https://github.com/danielmiessler/SecLists/blob/master/Fuzzing/LFI/LFI-gracefulsecurity-linux.txt)
*   Tested using fuzzing tools like `ffuf` or `Burp Intruder`and filtering out the genric error response size which was 18.

Press enter or click to view image in full size

![Image 8](https://miro.medium.com/v2/resize:fit:700/1*PilB1TD31d3rzlvpJDcfrA.png)

Checking the right payload to see how could I potentially find that!

Press enter or click to view image in full size

![Image 9](https://miro.medium.com/v2/resize:fit:700/1*To1dq5LCbQP8zw2kgys4gw.png)

Making that LFI list ready for the FUZZ

Press enter or click to view image in full size

![Image 10](https://miro.medium.com/v2/resize:fit:700/1*tKjnkQvhl3kCiq4X420jJw.png)

Three results were given back, checking them manually by curl, could reveal the vulnerable path.

This method would have revealed the vulnerability quickly when trying `/var/log/nginx/access.log`.

Press enter or click to view image in full size

![Image 11](https://miro.medium.com/v2/resize:fit:700/1*jpcOpc5IlfWXzUlGFXhw9A.png)

Nginx access.log revealed by LFI, many of us simply report it without further escalation :(

## Escalation the LFI and achieving the flag by Server-Side XSS (SSXSS)!!!

After discovering I could access the Nginx logs, I should have tested for HTML injection (`<script>`, `<iframe>`). I noticed these tags executed but didn't run visibly in my browser. More research and inspections showed me the server uses a **headless Chrome** to dynamically create PDFs from HTML files!!! This meant I was like interacting with Chrome's "Print as PDF" feature—but on the server!! something like when we do (ctrl+p) to print a webpage in chrome browser.

## Get Kianoush’s stories in your inbox

Join Medium for free to get updates from this writer.

Remember me for faster sign in

Now, I understand there was a browser on the server side creating PDFs from HTML contents, which I could control of its html contents and write arbitrary html codes to it!! I realized just at the time of conversion from html to pdf by that server side headless chrom browser, there is a chance of JavaScript execution and I could exploit this by making the browser run JavaScript that would access local files and include their contents in the PDF for me to read.

## Exploiting the Vulnerability

My goal became reading the `flag.txt`, likely located in the same directory as the temporary HTML file on the server. These two payloads could achieve this:

<iframe src='file:///flag.txt'></iframe>

Press enter or click to view image in full size

![Image 12](https://miro.medium.com/v2/resize:fit:700/1*GbboEhKRLF1xjNH--JQlBg.png)

Inserting the iframe payload to the User-Agent header

Press enter or click to view image in full size

![Image 13](https://miro.medium.com/v2/resize:fit:700/1*MROA3ywp_mDUw9ndim13-w.png)

Opening the access.log and see the flag in iframe window.

**OR**

<script>window.location='file:///flag.txt';</script>

Press enter or click to view image in full size

![Image 14](https://miro.medium.com/v2/resize:fit:700/1*EgQEQkfc-ltkmuJ27DJcOg.png)

Inserting a script tag with any random parameter value!

Press enter or click to view image in full size

![Image 15](https://miro.medium.com/v2/resize:fit:700/1*7xLhc8CPBzNANdCrQj0-Fg.png)

Opening the access.log and see the flag in a whole new window ( looks better :D )

To complete the second phase of the attack:

*   Send an HTTP request with one of these payloads (for example, in the User-Agent header or a custom fake parameter, or anywhere you like! it doesn’t really matter where you insert it or what status code you get 200, 400, etc. (whatever you do just make some logs on access.log) so that it can be rendered and executed by the server side chrome headless browser.
*   Load the PDF again from the vulnerable access.log endpoint to see the flag.

## A Common Mistakes

A common mistake others made was using double quotes (`"`) instead of single quotes (`'`). Nginx escapes double quotes (`\"`), breaking their payload URLs. Single quotes avoided this issue completely. here is what chatgpt says:

Press enter or click to view image in full size

![Image 16](https://miro.medium.com/v2/resize:fit:700/1*W28WC2FWtymKLXP4jxsz0w.png)

Double qoute is getting escaped by nginx as it’s a natural behaviour of it!

See what happenes:

Press enter or click to view image in full size

![Image 17](https://miro.medium.com/v2/resize:fit:700/1*pdgk6OYQRsj7ItFvrgo3Zw.png)

Sending the exact same iframe payload but using “ instead of ‘

Press enter or click to view image in full size

![Image 18](https://miro.medium.com/v2/resize:fit:700/1*UFkqd2R3SqmWoMyBhDt_mw.png)

Broken iframe result, as of nginx escaping “ and corrupting the payload

## Correct Name of the sceond phase vulnerability!

As this was neither a Server-Side Template Injection (SSTI) nor a command injection, and the vulnerable component was simply a Chrome browser running on the server side, I came up with the term “Server-Side Cross-Site Scripting (SSXSS).” :)

## Identifying PDFs Created by a Headless Browser

I’ve now added this approach to my **methodology**:

Next time when I see my inputs getting rendered and returned as a PDF, I will perform these quick checks:

1.   Check URL and content-type mismatch (for example, URL ends with `.html` but content-type is `application/pdf`).
2.   Inspect the PDF properties for signs like `Skia/PDF` (indicating Chrome-based headless rendering).
3.   Confirm that my inputs appear exactly within the PDF.

If everything matches, I will immediately test for Server-Side Cross-Site Scripting (SSXSS). Specifically, I’ll attempt to access locally stored files by fuzzing paths with this logic:

<iframe src='file:///FUZZ.FUZZ'></iframe>
OR

<script>window.location='file:///FUZZ.FUZZ';</script>
Thank you for staying with me throughout this write-up. I hope you enjoyed NahamCon CTF and learned prcielss lessons and tips as much as I did.

Cheers!
