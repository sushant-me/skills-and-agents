---
name: ctf-forensics-osint
description: Use for forensics, steganography, and OSINT challenges in a CTF — disk and memory images, pcap analysis, file carving, metadata and EXIF, LSB and appended-data steganography, password-protected archives, log reconstruction, and open-source-intelligence pivoting.
---

# Forensics, stego, OSINT

## Identify, always

```bash
file *                       # never trust the extension
binwalk -e suspicious.png    # embedded archives / filesystems
exiftool suspicious.jpg      # metadata is a hiding place, and often the flag
strings -n 8 -a file | grep -iE 'flag|ctf|secret|password'
xxd file | tail -20          # appended data after the real EOF
```

`file` disagreeing with the extension is itself the finding.

## Images / audio

- **LSB**: `zsteg` (PNG/BMP) first, then `stegsolve` to page through bit planes
  by eye. `stegseek` for steghide with a wordlist.
- **Appended data**: compare the header's declared size with the real file size.
- **JPEG**: `jpegsnoop`, or hidden data in EXIF comments.
- **Audio**: open the spectrogram (`audacity` → Spectrogram, or `sox`). Text
  drawn in a spectrogram and DTMF tones are the two classics.
- **QR / barcodes** in a corner: crop and decode.
- **PNG chunks**: `pngcheck -v` — a chunk after `IEND` is not part of the image.

## Archives

```bash
zip2john secret.zip > h && john h --wordlist=rockyou.txt
7z2john secret.7z > h && john h --wordlist=rockyou.txt
binwalk -e --run-as=root firmware.bin
```
Nested archives: loop. A zip inside a zip inside a zip is a real challenge shape.
For a corrupted zip, repair the central directory rather than giving up.

## Disk images

```bash
fdisk -l image.dd                  # partitions, before mounting anything
mmls image.dd                      # Sleuth Kit
fls -r -o <offset> image.dd        # deleted entries, recursively
icat -o <offset> image.dd <inode>  # recover one by inode
photorec image.dd                  # carve by signature, layout-independent
```
`autopsy` when the image is large and you want a UI. Deleted-but-recoverable is
the single most common disk-forensics flag.

## Memory images

```bash
vol -f mem.raw windows.info
vol -f mem.raw windows.pslist | grep -vE 'svchost|System'
vol -f mem.raw windows.cmdline
vol -f mem.raw windows.netscan
vol -f mem.raw windows.filescan | grep -i flag
vol -f mem.raw windows.dumpfiles --virtaddr 0x...
```
Look for: a process whose parent makes no sense, a suspicious command line, an
injected region (`windows.malfind`), or the flag file in `filescan`.

## PCAP

```bash
tshark -r cap.pcap -q -z io,phs                    # protocol hierarchy first
tshark -r cap.pcap -Y 'http.request' -T fields -e http.host -e http.request.uri
tshark -r cap.pcap --export-objects http,out/
```
Then, in order: **follow the TCP stream**, extract objects, and check for
credentials in plaintext protocols (FTP, HTTP basic, Telnet, SMTP). For USB
captures, `tshark` + the USB HID dissector reconstructs keystrokes. For TLS,
look for the key in the capture or in the memory image.

## Logs / misc

Grep for the flag **prefix** across everything early — many forensics flags are
simply present in a log once you look, and finding that in minute two saves the
event. Then reconstruct the timeline: `sort -k1,2` on timestamps, and diff
related logs against each other.

## OSINT

- **Reverse image search** first for any photo: Google Lens, Yandex, Bing.
- **EXIF GPS** → map coordinates. `exiftool -GPSPosition`.
- **Username pivot**: `sherlock`, `whatsmyname` to find the same handle elsewhere.
- **Metadata in documents**: author names, software versions, revision history,
  and `git log` on a leaked repo.
- **Wayback Machine** for a page's prior state; **crt.sh** for subdomains;
  **whois** and passive DNS for infrastructure.
- **Geolocation**: signs, licence plates, shop names, sun angle and shadow
  direction, and the language on signage. Corroborate with two independent
  sources before committing to a coordinate.

### The flag grammar is the challenge

OSINT flags are graded on an **exact string**, so a well-researched near-miss
scores exactly zero. Read the description's stated format as a schema and fill
every slot with evidence — never freehand the phrasing:

```
Null0rigin{OLD_COMPANY_NAME_DD_MM_YYYY_HH_MM}
NullOriginCTF{Restaurant_Name_Latitude_Longitude}      # 2 decimal places
Null0rigin{username1_username2}
```

- **Copy the prefix from the description, character by character.** `Null0rigin`,
  `NullOrigin`, and `NullOriginCTF` all appear across one event, and the zero in
  `Null0rigin` is an ASCII digit. A right answer under the wrong prefix is a
  wrong answer.
- **Match the requested precision literally.** "Rounded to 2 decimal places"
  means format the coordinate to two decimals; `27.7` and `27.70` are different
  strings.
- **Enumerate the slots before researching.** Knowing you need *old name* +
  *date* + *time* tells you to hunt three independent facts and only then
  assemble; discovering a missing slot after 40 minutes of geolocation is the
  common failure.
- **Verify each component against a second source.** One of them is usually a
  decoy — a similarly named place, a company's current rather than former name.

### Facts that hide in plain sight

- **Uploaded photos usually keep their EXIF.** Do not assume a social-media
  upload was stripped — check `DateTimeOriginal` and `GPSPosition` first. For
  "when was this captured", the answer is `DateTimeOriginal`, never the file
  mtime or the upload date.
- **"What was the company called before?"** is a history question: Wayback
  Machine snapshots of the about page, press releases, LinkedIn's former-name
  field, and archived job postings. The current name is the decoy.
- **Handle-pair challenges** (`user1_user2`) are about a *relationship*: find
  both accounts, then confirm the link from mutual tags, follows, or a shared
  photo — the pair is the answer, not either handle alone.
- **The event's own social accounts are in scope.** An OSINT sanity challenge
  frequently points at the organisers' Instagram or X profile; the bio, a story,
  or a tagged post carries it.
- **Log every candidate you reject.** OSINT has a long tail of plausible
  answers, and without a rejection list you will retry the same wrong restaurant
  twice.

## Discipline

Work on copies. For every artifact, record the one command that produced the
finding — a forensics flag you cannot reproduce is a flag you cannot explain in
a writeup, and CTF writeups are worth as much to a portfolio as the flag.
