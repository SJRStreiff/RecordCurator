
# RecordCurator

This pipeline consists of three somewhat independent but complementary steps:
* RECORDCLEANER:  takes raw occurrence records and cleans them to standardised format. The main feature here is that we merge duplicate collections, while retaining all the information of the different iso-specimens.
* COORDINATE-CHECK: takes the cleaned data, checks and flags coordinates with the *CoordinateCleaner* R-package (https://github.com/ropensci/CoordinateCleaner)
* RECORD-FILER:  integrates the data cleaned in RECORDCLEANER into a master database.


## Installation

To use recordcurator, clone this repository using
``` 
git clone https://github.com/SJRStreiff/RecordCurator
```

You need a number of python packages to run these scripts. We recommend to use a conda environment to install the dependencies.
WIth conda installed, navigate to your 'recordcurator' folder with the enclosed *'environment.yml'* file. Once there, execute the command *conda env create -f environment.yml*. By default, the environment will be named **recordcurator**, but you can change this in the first line of the environment.yml file.
Follow this up with *conda activate recordcurator*, followed by  *pip install pykew country-converter*. Now you are ready to start using the pipeline. I strongly recommend you look at the supplied configuration file *launch.sh*, where you can specify options, inputs and outputs. 



## Standardising occurrence records: RECORDCLEANER


To launch recordcleaner, you can use the useful bash launcher, in terminal in your directory: (if you haven't already, make the
bash file executable - first line below)

```
# chmod +x launch.sh
./launch.sh
```

The handy *launch.sh* script let's you specify your input and output options, as well as other important parameters.
Alternatively, the script can be called directly in the command line with the '-h' flag, which lets a user know exactly which parameters are required and which are optional.

```
> python ./3_scripts/recordcleaner.py -h

RECORDCLEANER takes your raw occurence records and compares them to an existing database if you have it, cleaning up column names, removing duplicates and making it more pleasing in general

positional arguments:
  input_file            Raw input file path
  {GBIF,P,BRAHMS,MO,RAINBIO}
                        File format. So far I can only handle Darwin core (GBIF) or herbonautes (P)
  {EXP,NO,SMALLEXP}     Specify if input file is of expert source (i.e. all determinations and coordinates etc. are to have priority over other/previous data)
  working_directory     the directory in which to deposit all intermediate working files. Files that need reviewing start with "TO_CHECK_"
  output_directory      the wished output directory
  prefix                prefix for ouput filenames

options:
  -h, --help            show this help message and exit
  -v VERBOSE, --verbose VERBOSE
                        If true (default), I will print a lot of stuff that might or might not help...
  -l LOG_FILE, --log_file LOG_FILE
                        path specifying a location for the output logfile.


If you have any questions, or would like to chat, feel free to contact me at serafin.streiff<at>ird.fr
```

The *launch.sh* script is formatted in a way, that the output of the **recordcleaner** step is automatically the input for the **coordinate-check** step, the output of which again is automatically the input for the **recordfiler** step.

## Working with RECORDCLEANER

### Input files

In it's present form, the pipeline only takes input file in either the "darwin core format", as for example found in GBIF data, or
the format used at P for their herbonautes citizen science projects (*Streiff & al., in prep*), the BRAHMS database format used at Naturalis or data
extracted from Tropicos. Alternatively, specially reduced expert data can be integrated using the 'SMALLEXP' flag in the expert_file parameter (see below).
GBIF raw data downloads are by default formatted as tab-separated tables, and herbonautes data is separated by semicolons ';'. 

### Working directory

The working directory is specified for collecting intermediate data outputs. This data subsets of the input data which is not reconcileable with the standardisation chosen, and therefore not filterable with some steps of the pipeline. However, a lot of this might be still useable. Therefore it is written into the working directory for manual editing of the steps that cannot be done automatically.

For example, when standardising collector names (which is crucial for detecting duplicate records in subsequent steps), I cannot handle names that are not in the format of some firstname, any middle names and some surname. E.g. if collections are filed under a program name (i.e. in SE-Asia, herbarium specimens are frequently labelled and numbered as something similar to "Forest Research Institute (FRI)", which I don't cleanly filter automatically). Therefore it is faster to manually cross check these for consistency within dataset, and then the records are reinserted easily.
Specifically during the 'Collector name' standardisation step, records that fail the automatic standardisation are output to a temporary file, and after this step the pipeline lets the
user know than one can edit the records before reinserting them and continuing. 

During deduplication, suspected duplicates with large variation between coordinates are written to a file for manual inspection,
and not kept in the pipeline (see below).

### Output directory

The output directory houses files that are written after each of the individual steps. These can be manually inspected for consistency and accuracy. These do not correspond to the master database, which can be stored anywhere you like (path specified in the *launch.sh* file).

## What does recordcurator really do?

#### RECORDCLEANER

RECORDCLEANER goes through a few iterative step, which I briefly expain here.

* Step A:
  * A1: Standardise column names, remove unwanted columns and add empty columns we need later
    *NB: postgreSQL only takes lowercase column names; As our implementation ends up as such a database, this is done as such in our code.*
  * A2: Standardise data within some columns, e.g. separate all dates into separate columns day, month and year, make sure all barcodes have the institution leading before the number, have the first collector in a separate column,
  * A3: Standardise collector names to  *Streiff, SJR*, instead of *Serafin J. R. Streiff* in one record and *Streiff, Serafin* in another record
  * A4:  Standardise collector names even more by querying the Harvard University Herbarium botanists
    [https://kiki.huh.harvard.edu/databases/botanist_index.html] database to get full or normalised names with a link to the
    record in that database (and wikipedia links for very famous botanists...). Names that are not found in that database are
    returned in the same format as the regex names (i.e. *Streiff, SJR*), whereas successfully found names are either returned as
    full names (*Surname, Firstname Any Middlename*) or abbreviated names (*Surname, F. A. M.*). The HUH database query is
    performed only with the surname, and results filtered with the original label data provided by the input data. HUH also
    returns, if available, information on collection regions of a botanist and wiki links.

* Step B:
  * B1: run some statistics on duplicates in the dataset. Select and remove all records where the collection number is a variation of 
    *s.n.*. These are then treated separately to the others with other criteria to find duplicated specimens.
  * B2: remove said duplicates. The duplicates are at the moment identified by the following criteria: If the collector name (mix of HUH where possible, and regex where not), number, number sufix and year are identical, they are flagged as duplicates.
  Note that records with no collection number (i.e. *s.n.*) are treated separately (B3) 
  * B3: remove duplicates from separated *s.n.* -records. Here more other values are taken into consideration,  the combination of Surname, Collection Year, Month and Day and Genus + specific_epithet are used to identify duplicates. This leads to errors, but in my humble opinion it's better than nothing.
  * B4: Crossfill country full name and ISO codes (needed later on, and not always complete.)

* Step C:
  * Check taxonomy for accurracy, and update if necessary. At the moment this is done by cross checking with POWO (powo.kew.org), which for our case is fairly up to date. With other plant families the situation might be different, but changes can always be integrated by getting in touch with the curators of POWO and making them aware of published taxonomic changes that might not be up to date.

#### COORDINATE-CHECK

  * This process is invoked as a separate step in R, as the packages available there are more used and robust. For the moment we implemented an automatic CoordinateCleaner (https://ropensci.github.io/CoordinateCleaner/index.html) run, which does not (!) remove problematic coordinates, but flags them. Many coordinates  are in the sea, but close to the coastline (i.e. distance less than 5000m, thus wihtin general uncertainty of coordinates and coastline shapefiles). These coordinates are automatically modified to take the value of the closest coastline coordinate.

The resulting data of these cleaning steps are the following files:
* FILENAME_cleaned.csv: final output from python processing (up to, including Step C1)
* FILENAME_spatialvalid.csv: final output with spatialvalid tag from *CoordinateCleaner*. Final data for import into database.

#### RECORD-FILER

RECORD-FILER then goes and takes freshly (or even old) cleaned data and tries to integrate it into a pre-existing database

* RECORD-FILER:
  * Merge newly cleaned data with the database. Before the actual merging, I check for duplicates and merge these 
  * First all databases are read. These include two backlog datasets, the *indet*-backlog and the *no-coordinate*-backlog, as well as the master database. Backups of these are saved with a timestamp, so any changes can easily be reverted.
  * With barcode priority, duplicates are checked and merged identically to the cleaning steps outlined above. If duplicates are found to with new data and the backlogs, these records are merged, and all data is saved into the new master version.
  * To speed up the computation, which is significant once a master database has many records, the data is subset by countries in the new input data, and remerged after processing.
  * Finally the newly modified backlogs and master database are saved.



# Special Options

## Expert data

CAUTION: this setting gives new data more priority than previous data. Therefore, make sure input data used with this flag is clean, validated and doesn't include missing data!

If the EXP=EXP in the config file, then the pipeline expects this dataset to be completely expert determined and curated. The values here are given precedence over duplicates found in the master database. The main utility of using this flag is to integrate this data to update any determinations and georeferencing.

If EXP=SMALLEXP, then records are found with the barcode, and any relevant data is overwritten with the new data. Make sure that
these datasets are therefore correct!
If EXP=SMALLEXP data is integrated with missing barcodes, then duplicates are checked for with the collector name and collection number of the specimens. 
NB: It is adviseable to remove any specimens with *s.n.*, as these are not specific enough to be sure the correct specimen is updated.


### SQL/postgres interface

A small script is provided which automatically up/downloads a master database from a postgres server (y_sql_functions.py).


# Common problems / error sources

Some data sources have aspects that can lead to errors in the pipeline. Usually these can be found by checking the error message
at or near the end of the log file, or in the terminal.
Common error sources are for example the occurrence of ';' within a cell which is not in quotes, or quote characters that are
misplaced (e.g. Coordinates in text written as e.g. 22°46'11\"N 104°49'07\"E, where the escape character \" is not correctly
identified.)
This leads to the message **Error tokenizing data.**, followed by a mention of the problematic line in the input file.  This can
be solved by manually editing the input. Open the csv-file in a texteditor, search-and-replace \" with e.g. \'

* make sure not to run 2 separate instances of the record-filer step simultaneously, as this might create a chaos between the
master database files! (N.B. this is less of an issue with the new version as it is much more rapid)

* If your job is killed by the system during *recordfiler*, potentially you have duplicated barcodes in the index. These are used as
index during some
deduplication steps. On my system the job is stuck for a minute or two before being stopped with the message 'Killed: 9'.
It occurs with expert data during the merge step. The exact cause is not quite clear to me as i have not been able to reliably
reproduce it, so if this
error does occur with your data, please let me know! 

# Future updates and modifications possible

For advanced users, one might change the columns to subset, for example to integrate data from other sources. The columns are specified in the
file "./3_scripts/z_dependencies.py". **It is crucialthat both the columns and their associated datatype are correctly specified
there.** 
Failure to do so will create problems when
working with the data. Details and data-source specific modifications necessary to standardise data can be changed in the script *z_functions_a.py*

I hope to add integraion of other databases, including linking e.g., to [Bionomia]{https://bionomia.net/}.
**more to come**
