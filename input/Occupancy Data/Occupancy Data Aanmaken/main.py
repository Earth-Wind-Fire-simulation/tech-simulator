from datetime import datetime

import numpy as np
import pandas as pd


#deze functie bepaalt welk dagtpye moet worden gebruikt voor de bezetting
def dagtype(dagst):

    #dag- en weeknummer bepalen b.v. vakantieperiodes
    weeknummer = dagst.isocalendar()[1]

    #zet in deze (zomer)vakantieperiode alle dagen op 'zondag'
    if weeknummer >= 27 and weeknummer <= 32:
        return 3  # vakantie = zondag

    # zet in deze (kerst)vakantieperiode alle dagen op 'zondag'
    if weeknummer == 52:
        return 3  # vakantie = zondag

    # retourneer anders 1 = werkdag, 2 = zaterdag of 3 = zondag
    if dagst.weekday() == 6:
        return 3
    if dagst.weekday() == 5:
        return 2
    return 1

#definitie van de bezetting (in procent) per uur voor ieder dagtype
werkdag = np.array([ 0,  0,  0,  0,  0,  0,
                     0,  0, 60, 60, 90, 90,
                    50, 50, 80, 80, 80, 50,
                    42, 33, 25, 17,  8,  0 ])
zaterdag = np.array([0,  0,  0,  0,  0,  0,
                     0,  0,  0,  0, 50, 50,
                    30, 30, 50, 50, 50,  0,
                     0,  0,  0,  0,  0,  0 ])
zondag = np.array([  0,  0,  0,  0,  0,  0,
                     0,  0,  0,  0,  0,  0,
                     0,  0,  0,  0,  0,  0,
                     0,  0,  0,  0,  0,  0 ])
dagtijd = range(24)

# Nieuw dataframe maken
df = pd.DataFrame()

# Creeer tijdstippen met tijdzone
jaar = 2025
print(jaar)
start = datetime(jaar, 1, 1, 0)
stop = datetime(jaar, 12, 31, 23)
df['date and time'] = pd.date_range(start, stop, freq='h', tz='Europe/Amsterdam')

for index in df.index:

    dagst = df.loc[index, 'date and time']

    df.loc[index, 'index'] = index
    df.loc[index, 'date'] = dagst.strftime("%d-%m-%Y")
    df.loc[index, 'month'] = dagst.month
    df.loc[index, 'day'] = dagst.day
    df.loc[index, 'weeknr'] = dagst.isocalendar()[1]
    df.loc[index, 'weekday(0=M)'] = dagst.weekday()
    df.loc[index, 'hour'] = dagst.hour

    df.loc[index, 'daytype(WrkSaSu)'] = dagtype(dagst)

    if dagtype(dagst) == 1:
        df.loc[index, 'occupancy(perc)'] = werkdag[dagst.hour]
    elif dagtype(dagst) == 2:
        df.loc[index, 'occupancy(perc)'] = zaterdag[dagst.hour]
    else:
        df.loc[index, 'occupancy(perc)'] = zondag[dagst.hour]

print(df)

# Dataframe opslaan
df.to_csv('Occupancy.csv', sep=";", decimal=",", index=False)

