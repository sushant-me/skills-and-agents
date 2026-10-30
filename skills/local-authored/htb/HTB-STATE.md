# HTB — state, written from the platform (agent-independent)

Generated **2026-09-30T11:57:52**. Source: live platform API: /v4/user/info, /experience/v1, /v4/user/profile/basic/<id>, /v5/machines, /v4/challenges, /v4/sherlocks

**Why this file exists:** two agents died mid-run this session and took their progress records with them.
Everything here is read from the platform, so it is correct whether or not any agent reports.

```
account        : nofear976   isVip=False   subscription=free   canAccessVIP=False
level          : 80  (Prodigy)      total XP: 95674
rank           : Hacker (rank_id=3)
machines       : system_owns=11  user_owns=14  owned user+root=11  of 553 total
challenges     : owned=116   submittable remaining=94
sherlocks      : complete=103 of 122 reachable (platform total 267)   tasks=1055
```

## The `isVip=false` ceilings — constraints, not failures
```
machines   : ~33 free of 553; the rest are VIP-gated
sherlocks  : 122 reachable of 267; 145 state=retired are VIP-only
challenges : 94 submittable remain of 855; 645 state=retired are permanently unobtainable
```

## Active / seasonal machines still unowned at root
```
  981    Management         Easy
  945    Orion              Easy
  921    Paperwork          Easy
  867    Silentium          Easy
  930    DarkZeroReturns    Hard
  862    Garfield           Hard
  951    Ghostlink          Hard
  912    Nimbus             Hard
  978    Scaffold           Hard
  864    Snapped            Hard
  975    BlockSynergy       Insane
  817    Eloquia            Insane
  954    Odyssey            Insane
  891    PingPong           Insane
  963    TrustFall          Insane
  927    Bedside            Medium
  909    Checkpoint         Medium
  936    DanglingTree       Medium
  903    DevHub             Medium
  984    Layover            Medium
  918    MakeSense          Medium
  853    Principal          Medium
```

## Season 12 note
Seasons track the **active** pool, not the retired content — so the machines above are the
seasonal target, and retired boxes (Fireflow, Abducted, SmartHire, Orion) do not count toward it.
