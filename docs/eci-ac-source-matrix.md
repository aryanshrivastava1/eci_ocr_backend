# ECI Assembly Constituency — source matrix (all 36 States/UTs)

`state_code` is the authoritative LGD State Code, stored as TEXT.
Generated from `data/reference/source/eci_ac_normalised.csv` on 2026-09-11.

| state_code | State/UT (LGD English) | Assembly? | ACs expected | Rows produced | Source of record | source_version | Status |
|---|---|---|---|---|---|---|---|
| 1 | Jammu And Kashmir | Yes | 90 | 0 | J&K Delimitation Commission Order, 2022 | not obtained | **UNRESOLVED** |
| 2 | Himachal Pradesh | Yes | 68 | 68 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 3 | Punjab | Yes | 117 | 117 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 4 | Chandigarh | No | 0 | 0 | — (no Legislative Assembly) | — | N/A |
| 5 | Uttarakhand | Yes | 70 | 70 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 6 | Haryana | Yes | 90 | 90 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 7 | Delhi | Yes | 70 | 70 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 8 | Rajasthan | Yes | 200 | 200 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 9 | Uttar Pradesh | Yes | 403 | 403 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 10 | Bihar | Yes | 243 | 243 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 11 | Sikkim | Yes | 32 | 31 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 12 | Arunachal Pradesh | Yes | 60 | 60 | ECI Delimitation Order, 2008 | `2008-currency-unconfirmed` | **UNRESOLVED** |
| 13 | Nagaland | Yes | 60 | 60 | ECI Delimitation Order, 2008 | `2008-currency-unconfirmed` | **UNRESOLVED** |
| 14 | Manipur | Yes | 60 | 60 | ECI Delimitation Order, 2008 | `2008-currency-unconfirmed` | **UNRESOLVED** |
| 15 | Mizoram | Yes | 40 | 40 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 16 | Tripura | Yes | 60 | 60 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 17 | Meghalaya | Yes | 60 | 60 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 18 | Assam | Yes | 126 | 126 | ECI Assam Delimitation Order, 2023 (**not obtained**); rows are 2008 | `2008-superseded-2023` | **UNRESOLVED** |
| 19 | West Bengal | Yes | 294 | 294 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 20 | Jharkhand | Yes | 81 | 81 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 21 | Odisha | Yes | 147 | 147 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 22 | Chhattisgarh | Yes | 90 | 90 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 23 | Madhya Pradesh | Yes | 230 | 230 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 24 | Gujarat | Yes | 182 | 182 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 27 | Maharashtra | Yes | 288 | 288 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 28 | Andhra Pradesh | Yes | 175 | 175 | ECI Delimitation Order, 2008 | `2008-undivided-ap-numbering` | **UNRESOLVED** |
| 29 | Karnataka | Yes | 224 | 224 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 30 | Goa | Yes | 40 | 40 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 31 | Lakshadweep | No | 0 | 0 | — (no Legislative Assembly) | — | N/A |
| 32 | Kerala | Yes | 140 | 140 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 33 | Tamil Nadu | Yes | 234 | 234 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 34 | Puducherry | Yes | 30 | 30 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 35 | Andaman And Nicobar Islands | No | 0 | 0 | — (no Legislative Assembly) | — | N/A |
| 36 | Telangana | Yes | 119 | 119 | ECI Delimitation Order, 2008 | `2008` | VERIFIED |
| 37 | Ladakh | No | 0 | 0 | — (no Legislative Assembly) | — | N/A |
| 38 | The Dadra And Nagar Haveli And Daman And Diu | No | 0 | 0 | — (no Legislative Assembly) | — | N/A |

Totals: **4032 rows**, 25 verified States/UTs, 6 unresolved, 5 with no Assembly.

## Why each unresolved entry is unresolved

- **Arunachal Pradesh** (`2008-currency-unconfirmed`) — Arunachal Pradesh was excluded from the 2008 Order under s.10A of the Delimitation Act, 2002; current legal instrument not established.
- **Nagaland** (`2008-currency-unconfirmed`) — Nagaland was excluded from the 2008 Order under s.10A; current legal instrument not established.
- **Manipur** (`2008-currency-unconfirmed`) — Manipur was excluded from the 2008 Order under s.10A; current legal instrument not established.
- **Assam** (`2008-superseded-2023`) — Superseded by the ECI Assam Delimitation Order, 11 Aug 2023 (126 ACs retained, 19 AC names revised). Order not obtained.
- **Andhra Pradesh** (`2008-undivided-ap-numbering`) — AC names and extents are current, but ac_number is the UNDIVIDED Andhra Pradesh number (120-294 contiguous). Post-2014 Andhra Pradesh numbers its 175 ACs 1-175. The offset appears to be -119 but that renumbering was NOT confirmed against an official source, so the source numbers are carried through unchanged.
- **Jammu And Kashmir** — 90 ACs expected, no rows. The 2008 Order carries J&K only as an Annexure reflecting the pre-2019 State (87 seats). Superseded by the J&K Delimitation Commission Order, 2022 (90 ACs), which was not obtained. The 2008 annexure is deliberately excluded rather than loaded as current.

## Expected missing rows (recorded, not fabricated)

- **Sikkim AC 32 — Sangha.** The Sangha constituency is non-territorial (electors are monks of registered monasteries). Schedule II counts it in Sikkim's 32 seats, but it has no entry in the district-wise Table A of the 2008 Order because it has no territorial extent. Not fabricated.

## District headings with no unambiguous LGD successor

These carry `mapping_confidence = needs_review` and an empty `district_lgd_code`.

| state_code | ECI district heading | Rows | Why |
|---|---|---|---|
| 14 | MANIPUR CENTRAL | 42 | pre-1990s district; Manipur has since been reorganised into 16 districts |
| 14 | MANIPUR EAST | 3 | pre-1990s district; no 1:1 LGD successor |
| 14 | MANIPUR NORTH | 6 | pre-1990s district; no 1:1 LGD successor |
| 14 | MANIPUR SOUTH | 6 | pre-1990s district; no 1:1 LGD successor |
| 14 | MANIPUR WEST | 3 | pre-1990s district; no 1:1 LGD successor |
| 17 | JAINTIA HILLS | 7 | split into East Jaintia Hills (657) and West Jaintia Hills (275) |
| 19 | BARDHAMAN | 25 | split into Purba Bardhaman (306) and Paschim Bardhaman (704) |
| 34 | MAHE REGION | 1 | Mahe is not present in the LGD district list snapshot |
| 34 | YANAM REGION | 1 | Yanam is not present in the LGD district list snapshot |

## Explicit district alias table (86 entries)

Hand-reviewed. No fuzzy matching decides a mapping; every target is asserted to exist in LGD at build time.

| state_code | ECI heading | LGD district (code) | Reason |
|---|---|---|---|
| 2 | SIRMOUR | Sirmaur (24) | spelling: Sirmaur |
| 3 | FIROZPUR | Ferozepur (31) | spelling: Ferozepur |
| 3 | MUKTSAR | Sri Muktsar Sahib (39) | renamed: Muktsar -> Sri Muktsar Sahib |
| 3 | NAWAN SHAHR | Shahid Bhagat Singh Nagar (40) | renamed: Nawanshahr -> Shahid Bhagat Singh Nagar |
| 5 | GARHWAL | Pauri Garhwal (52) | ECI "Garhwal" -> LGD Pauri Garhwal |
| 5 | HARDWAR | Haridwar (50) | spelling: Haridwar |
| 5 | RUDRYAPRAYAG | Rudraprayag (54) | spelling: Rudraprayag |
| 5 | UDHAMSINGH NAGAR | Udham Singh Nagar (56) | spelling: Udham Singh Nagar |
| 6 | GURGAON | Gurugram (62) | renamed: Gurgaon -> Gurugram |
| 9 | ALLAHABAD | Prayagraj (120) | renamed: Allahabad -> Prayagraj |
| 9 | BARABANKI | Bara Banki (129) | spelling: Bara Banki |
| 9 | BULANDSHAHAR | Bulandshahr (134) | spelling: Bulandshahr |
| 9 | FAIZABAD | Ayodhya (140) | renamed: Faizabad -> Ayodhya |
| 9 | JYOTIBA PHULE NAGAR | Amroha (154) | renamed: Jyotiba Phule Nagar -> Amroha |
| 9 | KUSHI NAGAR | Kushinagar (160) | spelling: Kushinagar |
| 9 | MAHAMAYA NAGAR | Hathras (163) | renamed: Mahamaya Nagar -> Hathras |
| 9 | MAHARAJGANJ | Mahrajganj (164) | spelling: Mahrajganj |
| 9 | SANT RAVIDAS NAGAR | Bhadohi (179) | renamed: Sant Ravidas Nagar -> Bhadohi |
| 10 | JAHANABAD | Jehanabad (199) | spelling: Jehanabad |
| 10 | PASCHIM CHAMPARAN | Pashchim Champaran (211) | spelling: Pashchim Champaran |
| 10 | PURVI CHAMPARAN | Purbi Champaran (213) | spelling: Purbi Champaran |
| 11 | EAST | Gangtok (225) | renamed: East -> Gangtok |
| 11 | NORTH | Mangan (226) | renamed: North -> Mangan |
| 11 | SOUTH | Namchi (227) | renamed: South -> Namchi |
| 11 | WEST | Gyalshing (228) | renamed: West -> Gyalshing |
| 15 | SAIHA | Siaha (267) | spelling: Siaha |
| 17 | RIBHOI | Ri Bhoi (276) | spelling: Ri Bhoi |
| 18 | MIKIR HILLS | Karbi Anglong (292) | renamed: Mikir Hills -> Karbi Anglong |
| 18 | NORTH CACHAR HILLS | Dima Hasao (299) | renamed: North Cachar Hills -> Dima Hasao |
| 18 | NOWGONG | Nagaon (297) | renamed: Nowgong -> Nagaon |
| 18 | SIBSAGAR | Sivasagar (300) | spelling: Sivasagar |
| 19 | COOCHBEHAR | Cooch Behar (308) | spelling: Cooch Behar |
| 19 | MALDAHA | Malda (316) | spelling: Malda |
| 19 | PURBO MEDINIPUR | Purba Medinipur (317) | spelling: Purba Medinipur |
| 20 | EAST SINGHBHUM | East Singhbum (327) | spelling: East Singhbum |
| 20 | KODARMA | Koderma (334) | spelling: Koderma |
| 20 | PAKAUR | Pakur (337) | spelling: Pakur |
| 20 | PALAMAU | Palamu (338) | spelling: Palamu |
| 21 | ANGUL | Anugola (344) | spelling: Anugola |
| 21 | BALASORE | Baleshwar (346) | spelling: Baleshwar |
| 21 | BARGARH | Baragada (347) | spelling: Baragada |
| 21 | BOLANGIR | Balangir (345) | spelling: Balangir |
| 21 | CUTTACK | Kataka (350) | spelling: Kataka |
| 21 | DEOGARH | Debagada (351) | spelling: Debagada |
| 21 | JAGATSINGHPUR | Jagatsinghapur (355) | spelling: Jagatsinghapur |
| 21 | KANDHAMAL | Kandhamala (359) | spelling: Kandhamala |
| 21 | KENDRAPARA | Kendrapada (360) | spelling: Kendrapada |
| 21 | KEONJHAR | Kendujhar (361) | spelling: Kendujhar |
| 21 | KHURDA | Khordha (362) | spelling: Khordha |
| 21 | NAYAGARH | Nayagada (367) | spelling: Nayagada |
| 21 | SUNDARGARH | Sundaragada (373) | spelling: Sundaragada |
| 22 | KABIRDHAM | Kabeerdham (382) | spelling: Kabeerdham |
| 22 | KORIA | Korea (384) | spelling: Korea (Koriya) |
| 23 | ASHOK NAGAR | Ashoknagar (391) | spelling: Ashoknagar |
| 23 | BADWANI | Barwani (393) | spelling: Barwani |
| 23 | EAST NIMAR KHANDWA | Khandwa (East Nimar) (405) | LGD form: Khandwa (East Nimar) |
| 23 | HOSHANGABAD | Narmadapuram (409) | renamed: Hoshangabad -> Narmadapuram |
| 23 | MANDSOUR | Mandsaur (416) | spelling: Mandsaur |
| 23 | NARSINGPUR | Narsimhapur (418) | spelling: Narsimhapur |
| 23 | WEST NIMAR KHAORGONE | Khargone (West Nimar) (414) | LGD form: Khargone (West Nimar) |
| 24 | BANASKANTHA | Banas Kantha (441) | spelling: Banas Kantha |
| 24 | PANCHMAHALS | Panch Mahals (454) | spelling: Panch Mahals |
| 24 | SABARKANTHA | Sabar Kantha (458) | spelling: Sabar Kantha |
| 27 | AHMEDNAGAR | Ahilyanagar (466) | renamed: Ahmednagar -> Ahilyanagar |
| 27 | AURANGABAD | Chhatrapati Sambhajinagar (469) | renamed: Aurangabad -> Chhatrapati Sambhajinagar |
| 27 | GONDIYA | Gondia (476) | spelling: Gondia |
| 27 | MUMBAI CITY | Mumbai (482) | LGD form: Mumbai |
| 27 | OSMANABAD | Dharashiv (488) | renamed: Osmanabad -> Dharashiv |
| 28 | ANANTAPUR | Ananthapuramu (502) | renamed: Anantapur -> Ananthapuramu |
| 28 | KADAPA | Y.S.R. Kadapa (504) | LGD form: Y.S.R. Kadapa |
| 28 | NELLORE | Sri Potti Sriramulu Nellore (515) | LGD form: Sri Potti Sriramulu Nellore |
| 29 | BAGALKOT | Bagalkote (524) | spelling: Bagalkote |
| 29 | BANGALORE | Bengaluru Urban (525) | renamed: Bangalore (Urban) -> Bengaluru Urban |
| 29 | BANGALORE RURAL | Bengaluru Rural (526) | renamed: Bangalore Rural -> Bengaluru Rural |
| 29 | BELGAUM | Belagavi (527) | renamed: Belgaum -> Belagavi |
| 29 | BELLARY | Ballari (528) | renamed: Bellary -> Ballari |
| 29 | BIJAPUR | Vijayapura (530) | renamed: Bijapur -> Vijayapura |
| 29 | CHICKMAGALUR | Chikkamagaluru (532) | renamed: Chikmagalur -> Chikkamagaluru |
| 29 | GULBARGA | Kalaburagi (538) | renamed: Gulbarga -> Kalaburagi |
| 29 | MYSORE | Mysuru (545) | renamed: Mysore -> Mysuru |
| 29 | SHIMOGA | Shivamogga (547) | renamed: Shimoga -> Shivamogga |
| 29 | TUMKUR | Tumakuru (548) | renamed: Tumkur -> Tumakuru |
| 34 | KARAIKAL REGION | Karaikal (598) | ECI "region" heading -> LGD district Karaikal |
| 34 | PUDUCHERRY REGION | Puducherry (600) | ECI "region" heading -> LGD district Puducherry |
| 36 | MAHBUBNAGAR | Mahabubnagar (512) | spelling: Mahabubnagar |
| 36 | RANGAREDDI | Ranga Reddy (518) | spelling: Ranga Reddy |
