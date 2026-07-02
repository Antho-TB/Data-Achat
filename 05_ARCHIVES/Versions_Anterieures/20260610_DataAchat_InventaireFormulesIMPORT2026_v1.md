# Inventaire des formules -- IMPORT 2026.xlsx
_Genere le 2026-06-10 (post-nettoyage, replica J-1)_

## Onglet `IMPORT 2025`

| Col | En-tête | Formule (pattern) | Occurrences |
|---|---|---|---|
| M | Nombre de mois  (de la commande à la livraison) | `=DATEDIF(C{r},AM{r},"M")` | 653 |
| P | Désignation | `=VLOOKUP(O{r},[1]Feuil2!$A:$M,5,FALSE)` | 651 |
| Q | Quantité | `=12520-5200` | 2 |
| Q | Quantité | `=1608-1308` | 2 |
| Q | Quantité | `=5000-1800` | 1 |
| Q | | _... 29 variante(s) supplementaire(s)_ | |
| S | Prix / référence | `=Q{r}*R{r}` | 656 |
| T | Total prix commande | `=SUMIF($E$5:$E$9173,E{r},$S$5:$S$9173)` | 610 |
| T | Total prix commande | `=SUMIF($E$5:$E$68,E{r},$S$5:$S$68)` | 46 |
| V | Total prix sur facture | `=U{r}+T{r}` | 656 |
| W | PCB | `=VLOOKUP(O{r},[1]Feuil2!$A:$M,6,FALSE)` | 656 |
| X | Volume m3  PCB | `=VLOOKUP(O{r},[1]Feuil2!$A:$M,13,FALSE)` | 656 |
| Y | Volume m3 réfernce total | `=(Q{r}/W{r})*X{r}` | 651 |
| Z | Volume m3 commande | `=SUMIF($E:$E,E{r},$Y:$Y)` | 656 |
| AJ | Retard  (jours) | `=DATEDIF(AI{r},$AJ$1,"D")` | 232 |
| AJ | Retard  (jours) | `=DATEDIF(AI{r},AK{r},"D")` | 122 |
| AJ | Retard  (jours) | `=DATEDIF(AI{r},$AK$383,"D")` | 4 |
| AJ | | _... 236 variante(s) supplementaire(s)_ | |
| AK | ETD réel | `=VLOOKUP(AP{r},'[2]CONTENEUR PLEIN'!$F:$L,3,FALSE)` | 469 |
| AK | ETD réel | `=VLOOKUP(AP{r},'[3]CONTENEUR PLEIN'!$F:$L,3,FALSE)` | 147 |
| AL | ETA | `=VLOOKUP(AP{r},'[2]CONTENEUR PLEIN'!$F:$L,5,FALSE)` | 469 |
| AL | ETA | `=VLOOKUP(AP{r},'[3]CONTENEUR PLEIN'!$F:$L,5,FALSE)` | 147 |
| AM | Date de livraison | `=VLOOKUP(AP{r},'[2]CONTENEUR PLEIN'!$F:$L,7,FALSE)` | 469 |
| AM | Date de livraison | `=VLOOKUP(AP{r},'[3]CONTENEUR PLEIN'!$F:$L,7,FALSE)` | 147 |
| AR | Transport | `=VLOOKUP(AP{r},'[2]CONTENEUR PLEIN'!$F:$L,2,FALSE)` | 621 |
| AR | Transport | `=VLOOKUP(AP{r},'[3]CONTENEUR PLEIN'!$F:$L,2,FALSE)` | 3 |

## Onglet `POINT MIF`

| Col | En-tête | Formule (pattern) | Occurrences |
|---|---|---|---|
| C |  | `=SUM(D{r}:I{r})` | 3 |

## Onglet `STOP REF CARREFOUR`

| Col | En-tête | Formule (pattern) | Occurrences |
|---|---|---|---|
| D | Quantité EN COMMANDE | `=2040+#REF!` | 1 |
