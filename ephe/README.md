# ephe/ — Swiss Ephemeris data files

These three files are the Swiss Ephemeris binary ephemeris files this service reads.

- Source: Astrodienst AG, Switzerland (Swiss Ephemeris). The file headers state:
  "Created for Astrodienst in Switzerland 2026/05/26, based on JPL Ephemeris DE441."
- Coverage used by this service: JD_UT 2378497.0 (1800-01-01) to 2597641.0 (2399-12-31).
- The service verifies the sha256 of each file at start-up and refuses to start on any mismatch.

| file | bytes | sha256 |
|---|---|---|
| seas_18.se1 | 223004 | `a2cd8fc33807c78ca9a700c91c2e042258b12fc4796519e00781440b5ad8b2e2` |
| semo_18.se1 | 1304771 | `1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7` |
| sepl_18.se1 | 484061 | `ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66` |

Do not edit, truncate or re-encode these files.

## Licence of the Swiss Ephemeris

The original Swiss Ephemeris licence file (`LICENSE` in the Swiss Ephemeris source tree as shipped
inside the `pyswisseph` 2.10.3.2 source distribution, `libswe/LICENSE`) is reproduced below without
change and also kept byte-for-byte as `SWISSEPH_LICENSE` next to this file. The copyright notice
must not be removed or altered. This repository is published under the GNU Affero General Public
License v3 (see `/LICENSE`), which is the AGPL branch of the dual licence below.

```text
/* Copyright (C) 1997 - 2021 Astrodienst AG, Switzerland.  All rights reserved.

  License conditions
  ------------------

  This file is part of Swiss Ephemeris.

  Swiss Ephemeris is distributed with NO WARRANTY OF ANY KIND.  No author
  or distributor accepts any responsibility for the consequences of using it,
  or for whether it serves any particular purpose or works at all, unless he
  or she says so in writing.  

  Swiss Ephemeris is made available by its authors under a dual licensing
  system. The software developer, who uses any part of Swiss Ephemeris
  in his or her software, must choose between one of the two license models,
  which are
  a) GNU Affero General Public License (AGPL)
  b) Swiss Ephemeris Professional License

  The choice must be made before the software developer distributes software
  containing parts of Swiss Ephemeris to others, and before any public
  service using the developed software is activated.

  If the developer choses the AGPL software license, he or she must fulfill
  the conditions of that license, which includes the obligation to place his
  or her whole software project under the AGPL or a compatible license.
  See https://www.gnu.org/licenses/agpl-3.0.html

  If the developer choses the Swiss Ephemeris Professional license,
  he must follow the instructions as found in http://www.astro.com/swisseph/ 
  and purchase the Swiss Ephemeris Professional Edition from Astrodienst
  and sign the corresponding license contract.

  The License grants you the right to use, copy, modify and redistribute
  Swiss Ephemeris, but only under certain conditions described in the License.
  Among other things, the License requires that the copyright notices and
  this notice be preserved on all copies.

  Authors of the Swiss Ephemeris: Dieter Koch and Alois Treindl

  The authors of Swiss Ephemeris have no control or influence over any of
  the derived works, i.e. over software or services created by other
  programmers which use Swiss Ephemeris functions.

  The names of the authors or of the copyright holder (Astrodienst) must not
  be used for promoting any software, product or service which uses or contains
  the Swiss Ephemeris. This copyright notice is the ONLY place where the
  names of the authors can legally appear, except in cases where they have
  given special permission in writing.
*/


```
