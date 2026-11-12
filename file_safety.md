# Bestandsbeveiliging bij het lezen van CSV-bestanden

## Achtergrond

Bij het selecteren van CSV-bestanden in Grasshopper werden bestanden verwijderd of vergrendeld doordat de Python-componenten ze direct lazen. De kernmodules lezen de invoerbestanden daarom via een tijdelijke kopie.

## Huidige werking

Dit geldt voor [src/weather.py](src/weather.py) (`safe_read_csv`) en [src/occupancy.py](src/occupancy.py) (`calculate_occupancy`). Beide gebruiken dezelfde CSV-lezer:

1. Het pad wordt gecontroleerd (niet leeg, niet `<null>`).
2. Per aanroep wordt een eigen map in de tijdelijke opslag van het besturingssysteem gemaakt. Daarin staat een kopie van het invoerbestand.
3. De kopie wordt gelezen met `pd.read_csv` (`sep=";"`; voor bezetting ook `decimal=","`).
4. De contextmanager ruimt de eigen kopie en tijdelijke map op, ook wanneer het lezen mislukt. Het origineel en bestaande buur-bestanden blijven ongewijzigd.

Foutafhandeling:

| Situatie | Uitzondering |
| --- | --- |
| Bestand niet gevonden tijdens kopiëren | `DataFileError` (`create_file_not_found_error`) |
| Geen toegang tijdens kopiëren of lezen | `DataFileError` (`create_permission_error`) |
| Ontbrekend of ongeldig pad | Pydantic `ValidationError` (via `WeatherPath`) |
| Overige leesfouten | `ProcessingError` |

Uitzonderingen uit `EWFException` worden niet opnieuw verpakt, zodat de specifieke melding bij de aanroeper aankomt. Ook padvalidatiefouten worden rechtstreeks door Pydantic opgegooid; ze worden niet omgezet naar `src/exceptions.py`.

## Beperkingen

- Leesrechten op de bron en schrijfrechten in de tijdelijke opslag blijven nodig; schrijfrechten in de bronmap zijn niet meer nodig.
- Een ander proces kan het bronbestand wijzigen terwijl het wordt gekopieerd. De kopie is geen transactie of bestandsslot op de bron.
- Een procescrash of besturingssysteemfout kan tijdelijke bestanden achterlaten. Een parsefout tijdens het lezen en gelijktijdige lezers worden afgedekt door regressietests; andere foutscenario's zijn niet volledig getest.
