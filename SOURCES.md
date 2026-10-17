# Sources and licences

Every directory under `skills/` is vendored from an upstream repository, at the
revision recorded below. The upstream `LICENSE` file is kept inside each
directory; nothing here relicenses it.

| Directory | Upstream | Licence | Skills |
| --- | --- | --- | --- |
| `mukul975_Anthropic-Cybersecurity-Skills` | https://github.com/mukul975/Anthropic-Cybersecurity-Skills | Apache-2.0 | 818 |
| `trailofbits_skills` | https://github.com/trailofbits/skills | CC BY-SA 4.0 | 85 |
| `SnailSploit_Claude-Red` | https://github.com/SnailSploit/Claude-Red | MIT | 80 |
| `transilienceai_communitytools` | https://github.com/transilienceai/communitytools | MIT | 50 |
| `crazyMarky_pentest-skills` | https://github.com/crazyMarky/pentest-skills | Apache-2.0 | 11 |
| `Eyadkelleh_awesome-skills-security` | https://github.com/Eyadkelleh/awesome-skills-security | **NO LICENCE DECLARED** | 7 |
| `x-glacier_kali-pentest` | https://github.com/x-glacier/kali-pentest | Apache-2.0 | 2 |
| `Gabson0x_bountyforge` | https://github.com/Gabson0x/bountyforge | **NO LICENCE DECLARED** | 1 |
| `shaniidev_bug-reaper` | https://github.com/shaniidev/bug-reaper | MIT | 1 |

Total vendored: 1,055 skills across the nine collections above.

The `ctf-operator` agent preset under `agents/` additionally carries 14 CTF
skills of its own, for **1,069 skills in the repository**.

## Two directories carry no licence

`Eyadkelleh_awesome-skills-security` and `Gabson0x_bountyforge` do not ship a
licence file, which by default means the authors reserve all rights. They are
included here because this repository is **private and used as an archive**.
If it is ever made public, remove those two directories first:

    git rm -r skills/Eyadkelleh_awesome-skills-security skills/Gabson0x_bountyforge

## CC BY-SA 4.0

`trailofbits_skills` is share-alike. Keeping it as an unmodified vendored
directory preserves its notice; any adaptation of those files must stay under
CC BY-SA 4.0.
