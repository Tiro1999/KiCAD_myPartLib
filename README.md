# KiCAD_myPartLib

Eigene KiCad-Symbole, Footprints und 3D-Modelle. Ergänzung zur offiziellen KiCad-Library, kein Ersatz dafür.

Ziel-Version: KiCad 10.

## Einrichten

Einmal pro Rechner: Repo klonen, dann in KiCad drei Einstellungen setzen.

1. **Einstellungen → Pfade konfigurieren**

   ```
   TIRO_LIB = S:/Data/KiCAD/Librarys/KiCAD_myPartLib
   ```

   Schrägstriche nach vorn, auch unter Windows.

2. **Einstellungen → Symbolbibliotheken verwalten → +**

   ```
   Nickname: Tiro
   Typ:      Table
   Pfad:     ${TIRO_LIB}/sym-lib-table
   ```

3. **Einstellungen → Footprintbibliotheken verwalten → +**

   ```
   Nickname: Tiro
   Typ:      Table
   Pfad:     ${TIRO_LIB}/fp-lib-table
   ```

Damit sind alle Tiro-Libraries auf einmal eingebunden. Die beiden Tabellen liegen im Repo. Kommt per `git pull` eine neue Kategorie dazu, reicht ein Neustart von KiCad.

## Struktur

```
KiCAD_myPartLib/
├── sym-lib-table                          alle Tiro-Symbol-Libraries
├── fp-lib-table                           alle Tiro-Footprint-Libraries
├── bootstrap.ps1                          legt neue Kategorien an
├── symbols/
│   └── Tiro_<Kategorie>.kicad_symdir/     eine .kicad_sym pro Symbol
├── footprints/
│   └── Tiro_<Kategorie>.pretty/           eine .kicad_mod pro Footprint
├── 3dmodels/
│   └── Tiro_<Kategorie>.3dshapes/         eine .step pro Footprint
└── datasheets/                            Quellen für angelegte Teile
```

Die drei Library-Ordner spiegeln sich im Namen. `Tiro_PWR` existiert in allen dreien oder in keinem. Dadurch lässt sich jede Referenz per Namenslookup auflösen statt per Suche.

KiCad 10 lädt einen Ordner mit einzelnen `.kicad_sym`-Dateien als eine Library: ein Symbol pro Datei statt vieler Symbole in einer Datei. Ein Merge-Konflikt betrifft damit ein Bauteil, nicht die halbe Library. Die Endung `.kicad_symdir` verlangt KiCad nicht, sie ist Konvention, passend zu `.pretty` und `.3dshapes`.

## Kategorien

In KiCad ist der Library-Name die Kategorie. Verschachtelte Unterordner gibt es in der Bauteilauswahl nicht. Feinere Sortierung läuft über Description und Keywords.

Neue Kategorien werden erst angelegt, wenn das erste Bauteil hineinkommt. Von Anfang an vorhanden: Mechanical, Connector, PWR.

| Nickname          | Inhalt |
|-------------------|--------|
| `Tiro_Mechanical` | Montagebohrungen, Castellated-Leisten, Fiducials, Testpunkte, Logos, Bohrschablonen |
| `Tiro_Connector`  | Stiftleisten, Buchsen, JST, USB, FFC/FPC, Schraubklemmen, Kartenslots |
| `Tiro_PWR`        | LDO, DC/DC, Spannungsreferenzen, Laderegler, Power-Path, eFuse, Schutzbeschaltung |
| `Tiro_Discrete`   | MOSFET, BJT, Dioden, TVS, Optokoppler, Relais |
| `Tiro_Passive`    | wertkonkrete R/C/L, Ferrite (nur bei atomarer Arbeitsweise) |
| `Tiro_Timing`     | Quarze, Oszillatoren, RTC |
| `Tiro_MCU`        | Mikrocontroller und MCU-Module |
| `Tiro_Memory`     | EEPROM, Flash, FRAM, SD-/microSD-Halter |
| `Tiro_Analog`     | OpAmps, Komparatoren, ADC, DAC, Analogschalter |
| `Tiro_Logic`      | Gatter, Pegelwandler, IO-Expander, Multiplexer, Schieberegister |
| `Tiro_Interface`  | USB-Bridges, CAN, RS485, Ethernet-PHY, Isolatoren |
| `Tiro_Sensor`     | Temperatur, Feuchte, IMU, Licht, Druck, Strom, Hall |
| `Tiro_Display`    | OLED, LCD, Segmentanzeigen, LED-Treiber, LEDs |
| `Tiro_RF`         | Funkmodule, Antennen, Baluns |
| `Tiro_Module`     | fertige Fremdmodule und Breakouts als Einheit |

### Neue Kategorie anlegen

```powershell
pwsh .\bootstrap.ps1 -NewLibrary Sensor -Description "Temperatur, Feuchte, IMU, Licht, Druck, Strom, Hall"
```

Mit Windows PowerShell 5.1 statt PowerShell 7:

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -NewLibrary Sensor
```

Das Skript legt die drei Ordner an und trägt die Library in beide Tabellen ein. Existiert die Library schon, bricht es ohne Änderung ab. Danach KiCad neu starten.

Kategorien nicht über „Neue Bibliothek“ in KiCad anlegen: KiCad erzeugt dabei eine einzelne `.kicad_sym`-Datei und trägt sie mit festem Pfad in die globale Tabelle ein statt ins Repo.

Wird eine Kategorie unübersichtlich, wird sie gesplittet (`Tiro_PWR` → `Tiro_PWR_LDO`, `Tiro_PWR_DCDC`). Vorher nicht.

## Arbeitsweise: atomar, mit einer Ausnahme

Atomar heißt: ein Symbol pro kaufbarem Bauteil, mit fest hinterlegtem Footprint, MPN und Hersteller. Die BOM fällt dann korrekt und ohne Nacharbeit aus dem Schaltplan. Das gilt für alles in diesem Repo.

Ausnahme: Widerstände, Kondensatoren und Spulen ohne besondere Anforderung kommen generisch aus der offiziellen Device-Library, Wert und Footprint werden im Schaltplan gesetzt. 300 Widerstandswerte atomar anzulegen lohnt sich nicht. `Tiro_Passive` ist nur für Passive mit harter Anforderung gedacht, etwa ein Shunt mit definierter Toleranz und Belastbarkeit.

## Varianten über Vererbung

Bauteile, die sich nur in einem Parameter unterscheiden, werden abgeleitet statt kopiert. Das Elternsymbol trägt die Grafik und die Pins, das Kind nur die abweichenden Feldwerte:

```
AP7343D.kicad_sym       (symbol "AP7343D" ...)              ← Grafik + Pins
AP7343D-33.kicad_sym    (symbol "AP7343D-33" (extends "AP7343D") ...)
AP7343D-25.kicad_sym    (symbol "AP7343D-25" (extends "AP7343D") ...)
```

Ein abgeleitetes Symbol ist ohne sein Elternsymbol nicht nutzbar. Beide Dateien gehören in dieselbe Library.

## Namenskonventionen

Symbole heißen wie die Herstellernummer ohne Verpackungssuffix: `AP7343D-33FS4`, nicht `AP7343D-33FS4-7B`. Das `-7B` ist nur Tape-and-Reel und gehört als Bestellnummer in ein Feld, nicht in den Namen.

Footprints folgen dem Stil der offiziellen Library: `<Grundform>_<Pins>_<Pitch>[_Variante]`

```
Castellated_1x06_P2.54mm
Castellated_1x06_P2.54mm_Edge
MountingHole_2.7mm_M2.5_Pad_GND
```

3D-Modelle heißen exakt wie ihr Footprint, Endung `.step`.

Erlaubte Zeichen in allen Namen: `A-Z a-z 0-9 _ - .` Keine Leerzeichen, keine Umlaute, keine Schrägstriche. Kategorienamen zusätzlich ohne Punkt.

## Pflichtfelder pro Symbol

| Feld         | Beispiel                          | sichtbar |
|--------------|-----------------------------------|----------|
| Reference    | `U`                               | ja       |
| Value        | `AP7343D-33FS4`                   | ja       |
| Footprint    | `Package_TO_SOT_SMD:SOT-23-5`     | nein     |
| Datasheet    | direkte PDF-URL des Herstellers   | nein     |
| Description  | `LDO 300 mA, 3.3 V fix, SOT-23-5` | nein     |
| Manufacturer | `Diodes Incorporated`             | nein     |
| MPN          | `AP7343D-33FS4-7B`                | nein     |
| LCSC         | optional, für JLCPCB-Bestückung   | nein     |

Description und Keywords sind das, was die Bauteilsuche durchsucht. Sie sind der Ersatz für die fehlenden Unterkategorien und entsprechend sorgfältig zu füllen.

## Eigene Footprints: nur wenn nötig

Vor jedem neuen Footprint wird geprüft, ob die offizielle Library ihn schon hat. Ein SOT-23-5 wird nicht nachgebaut. Erwartet wird, dass `footprints/` dauerhaft klein bleibt und im Wesentlichen `Tiro_Mechanical.pretty` enthält.

Muss ein offizieller Footprint angepasst werden: in der eigenen Library unter neuem Namen speichern und dort ändern. Fremdlibraries werden nie direkt editiert, die Änderung wäre beim nächsten `git pull` weg.

## Ein Bauteil hinzufügen

1. Datenblatt als PDF nach `datasheets/<MPN>.pdf` legen
2. Prüfen, ob der Footprint schon offiziell existiert
3. Symbol anlegen: Symbol-Editor → Rechtsklick auf die passende `Tiro_`-Library → Neues Symbol, Pflichtfelder ausfüllen
4. Falls nötig Footprint anlegen: Footprint-Editor → Rechtsklick auf die Library → Neuer Footprint, Maße gegen das Recommended Land Pattern im Datenblatt nachrechnen
5. Footprint 1:1 ausdrucken und das Bauteil drauflegen
6. 3D-Ansicht prüfen
7. Commit mit `add(<Kategorie>): <MPN>`
