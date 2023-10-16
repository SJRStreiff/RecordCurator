#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Functions for expert det

2023-08-23 sjrs


- format input data

- check for missing data etc.

- integrate with master/find duplicated BC
"""

import codecs
import pandas as pd
import numpy as np
import logging
import pykew.ipni as ipni
import swifter              # not used at the moment


from pykew.ipni_terms import Filters as ipni_filter
from pykew.ipni_terms import Name as ipni_name              # for taxonomic additional info
from tqdm import tqdm                                       # progress bar for loops

def read_expert(importfile, verbose=True):
    """
    read file, check columns
    """
    print('EXPERT file integration. \n',
          'Please assure that your columns are the following:',
          'ddlat, ddlong, locality, country or ISO2, recorded_by, colnum_full, det_by, det_date, barcode')
    imp = codecs.open(importfile,'r','utf-8')
    exp_dat = pd.read_csv(imp, sep = ';',  dtype = str)
    exp_dat['source_id'] = 'specialist'

    # make prefix from colnum
    exp_dat['prefix'] = exp_dat.colnum_full.str.extract('^([a-zA-Z]*)')
    exp_dat['prefix'] = exp_dat['prefix'].str.strip()

    # make sufix from colnum
    # going from most specific to most general regex, this list takes all together in the end
    regex_list_sufix = [
        r'(?:[a-zA-Z ]*)$', ## any charcter at the end
        r'(?:SR_\d{1,})', ## extract 'SR_' followed by 1 to 3 digits
        r'(?:R_\d{1,})', ## extract 'R_' followed by 1 to 3 digits
    ]
    exp_dat['sufix'] = exp_dat['colnum_full'].astype(str).str.extract('(' + '|'.join(regex_list_sufix) + ')')
    exp_dat['sufix'] = exp_dat['sufix'].str.strip()

    # extract only digits without associated stuff, but including some characters (colNam)
    regex_list_digits = [
        r'(?:\d+\-\d+\-\d+)', # of structure 00-00-00
        r'(?:\d+\s\d+\s\d+)', # 00 00 00 or so
        r'(?:\d+\.\d+)', # 00.00
        r'(?:\d+)', # 00000
    ]
    exp_dat['colnum']  = exp_dat.colnum_full.str.extract('(' + '|'.join(regex_list_digits) + ')')
    exp_dat['colnum'] = exp_dat['colnum'].str.strip()



# det date
    exp_dat[['det_year', 'det_month', 'det_day']] = exp_dat['det_date'].str.split("-", expand=True)



    exp_dat[['huh_name', 'geo_col', 'wiki_url']] = '0'
    exp_dat['orig_recby'] = exp_dat['recorded_by']
    exp_dat['col_year'] = pd.NA

    return exp_dat


# do HUH
# get ipni numbers?




# deduplication....
# we will do this by barcodes and or recorded_by + colnum + ??

def deduplicate_small_experts(master_db, exp_dat, verbose=True):
    """
    Find duplicates based on barcode, and collector name,

    Any values in these records found are overwritten by 'expert' data. This is assuned to be of (much) better quality.
    """

    # first some housekeeping: remove duplicated barcodes in input i.e. [barcode1, barcode2, barcode1] becomes [barcode1, barcode2]
    exp_dat.barcode = exp_dat.barcode.apply(lambda x: ', '.join(set(x.split(', '))))    # this combines all duplicated barcodes within a cell
    master_db.barcode = master_db.barcode.apply(lambda x: ', '.join(set(x.split(', '))))    # this combines all duplicated barcodes within a cell

    # drop any determinations that are empty. This would make a mess.
    exp_dat = exp_dat[pd.notna(exp_dat.accepted_name)] 
    # add column for flag if data found or not
    exp_dat['matched'] = '0'

    #----- prep barcodes (i.e. split multiple barcodes into seperate values <BC001, BC002> --> <BC001>, <BC002>)
    # split new record barcode fields (just to check if there are multiple barcodes there)
    bc_dupli_split = exp_dat['barcode'].str.split(',', expand = True) # split potential barcodes separated by ','
    bc_dupli_split.columns = [f'bc_{i}' for i in range(bc_dupli_split.shape[1])] # give the columns names..
    bc_dupli_split = bc_dupli_split.apply(lambda x: x.str.strip())
    # some information if there are issues
    logging.debug(f'NEW OCCS:\n {bc_dupli_split}')
    logging.debug(f'NEW OCCS:\n {type(bc_dupli_split)}')
    # repeat for master data
    # split potential barcodes separated by ','
    master_bc_split = master_db['barcode'].str.split(',', expand = True) 
    master_bc_split.columns = [f'bc_{i}' for i in range(master_bc_split.shape[1])]
    master_bc_split = master_bc_split.apply(lambda x: x.str.strip())  # strip all leading/trailing white spaces!
    logging.debug(f'master OCCS:\n {master_bc_split}')

    # to make an exceptions dataframe get structure from master
    exceptions = master_db.head(1)

    # for progress bar in console output
    total_iterations = len(exp_dat)
    print('Crosschecking barcodes...\n', total_iterations, 'records in total.')
    for i in tqdm(range(total_iterations), desc = 'Processing', unit= 'iteration'):
        # the tqdm does the progress bar

        barcode = list(bc_dupli_split.loc[i].astype(str))
            # logging.info(f'BARCODE1: {barcode}')
        # if multiple barcodes in the barcode field, iterate across them
        for x in  range(len(barcode)):
            bar = barcode[x]
            if bar == 'None':
                # this happens a lot. skip if this is the case.
                a = 'skip'
                #logging.info('Values <None> are skipped.')
            else:
                selection_frame = pd.DataFrame()  # df to hold resulting True/False mask  
                # now iterate over columns to find any matches
                for col in master_bc_split.columns:
                    # iterate through rows. the 'in' function doesn't work otherwise
                    #logging.info('checking master columns')
                    f1 = master_bc_split[col] == bar # get true/false column
                    selection_frame = pd.concat([selection_frame, f1], axis=1) # and merge with previos columns
                # end of loop over columns

                # when selection frame finished, get out the rows we need including master value
                sel_sum = selection_frame.sum(axis = 1)
                sel_sum = sel_sum >= 1 # any value >1 is a True == match of barcodes between dataframes 
            
                if sel_sum.sum() == 0:
                    # logging.info('NO MATCHES FOUND!')
                    out_barcode = pd.DataFrame([bar])

                # in this case we do not modify anything!

                else:
                    out_barcode = pd.Series(master_db.barcode[sel_sum]).astype(str)
                    out_barcode.reset_index(drop = True, inplace = True)


                # replace i-th element of the new barcodes with the matched complete range of barcodes from master
            
                input = str(exp_dat.at[i, 'barcode'])
                master = str(out_barcode[0])
                new = input + ', ' + master

                # reduce duplicated values
                new = ', '.join(set(new.split(', ')))

                # QUICK CHECK if recorded by and colnum are identical. Flag and save to special file if not
                print('1', master_db.loc[sel_sum, 'recorded_by'].item())
                print('2', exp_dat.loc[i, 'recorded_by'])
                if master_db.loc[sel_sum, 'recorded_by'].item() == (exp_dat.loc[i, 'recorded_by']):

                    #----------------------- Imperative Values. Missing is not allowed ----------------------#
                    if exp_dat.loc[i,['accepted_name', 'det_by', 'det_year']].isna().any() == True:
                        # make a visible error message and raise exception (abort)
                        print('\n#--> Something is WRONG here:\n',
                              '\n#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#\n',
                              exp_dat.loc[i,['accepted_name', 'det_by', 'det_year']],
                              '\n#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#\n',
                              '\n I am aborting the program. Please carefully check your input data.\n',
                              '\n#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#\n',)
                        raise(Exception('One of \'accepted_name\', \'det_by\', or \'det_year\' is NA.\n',
                                        'I do not allow such records as expert data....'))
                    # otherwise the crucial data is here so we can proceed...
                    master_db.loc[sel_sum, 'barcode'] = new
                    master_db.loc[sel_sum, 'accepted_name'] = exp_dat.at[i, 'accepted_name'] 
                    master_db.loc[sel_sum, 'det_by'] = exp_dat.at[i, 'det_by'] 
                    master_db.loc[sel_sum, 'det_year'] = exp_dat.at[i, 'det_year'] 
                    
                    #----------------------- Facultative Values. Missing is allowed --------------------------#
                    if ~np.isnan(exp_dat.loc[i, 'ddlat']):
                        master_db.loc[sel_sum, 'ddlat'] = exp_dat.at[i, 'ddlat'] 
                    if ~np.isnan(exp_dat.loc[i, 'ddlong']):
                        master_db.loc[sel_sum, 'ddlong'] = exp_dat.at[i, 'ddlong'] 

                    #----------------------- Automatic Values. Filled anyway --------------------------#
                    master_db.loc[sel_sum, 'status'] = 'ACCEPTED'
                    master_db.loc[sel_sum, 'expert_det'] = 'A_expert_det_file'
                    master_db.loc[sel_sum, 'prefix'] = exp_dat.at[i, 'prefix'] 

                    #----------------------- Cosmetic Values. Missing is allowed --------------------------#
                    # print((pd.Series(exp_dat.loc[i, 'colnum_full']).isin(['-9999','NA','<NA>','NaN'])).any())
                    # print('CNF', exp_dat.loc[i, 'colnum_full'])
                    if pd.Series(exp_dat.loc[i, 'colnum_full']).isna().any():
                        print('yes NA')
                        master_db.loc[sel_sum, 'colnum_full'] = exp_dat.at[i, 'colnum_full'] 
                    if pd.Series(exp_dat.loc[i, 'locality']).isna().any():
                        master_db.loc[sel_sum, 'locality'] = exp_dat.at[i, 'locality'] 

                    exp_dat.loc[i, 'matched'] = 'FILLED'


                else:
                    # exception where 'recorded_by' do not match
                    new_except = pd.concat([master_db.loc[sel_sum], pd.DataFrame(exp_dat.loc[i]).transpose()]) # see if this works...
                    # drop the offending rows for manual editing and adding later
                    master_db = master_db.loc[~sel_sum]
                    try:
                        # if exception already exists add concat
                        exceptions  = pd.concat([exceptions, new_except])
                    except:
                        # otherwise new 
                        exceptions = new_except
                # at the end of for loop print exceptions to file, let me manually redo it.
    print('MATCHED?', exp_dat.matched)
    exp_dat_to_integrate = exp_dat[exp_dat.matched != 'FILLED']
    print(exp_dat_to_integrate)

    # as we may have some data remaining, we just append it ot the master, as it's expert perfect ( in theory for our purposes)
    master_db =  pd.concat([master_db, exp_dat_to_integrate])
    ## TODO## TODO## TODO## TODO## TODO## TODO## TODO## TODO## TODO## TODO

    return master_db, exceptions


def integrate_exp_exceptions(integration_file, exp_dat):
    """
    read and concatenate data manually edited, chekc data lengths 
    """
    imp = codecs.open(integration_file,'r','utf-8') #open for reading with "universal" type set
    re_exp = pd.read_csv(imp, sep = ';',  dtype = str, index_col=0) # read the data
    try:
        new_exp_dat = pd.concat([re_exp, exp_dat])
        if len(new_exp_dat) == (len(re_exp) + len(exp_dat)):
            print('Reintegration successful.')
            logging.info('reintroduction successful')
        else:
            print('reintegration not successful.')
            logging.info('reintegration unsuccessful')
    
    except:
        new_exp_dat = exp_dat
        print('reintegration not successful.')
        logging.info('reintegration unsuccessful')

    return new_exp_dat




def expert_ipni(species_name):
    ''' 
    Check species names against IPNI to get publication year, author name and IPNI link

    INPUT: 'genus'{string}, 'specific_epithet'{string} and 'distribution'{bool}
    OUTPUT: 'ipni_no' the IPNI number assigned to the input name
            'ipni_yr' the publication year of the species

    '''
    #print('Checking uptodate-ness of nomenclature in your dataset...')

    query = species_name
        #print(query)
    res = ipni.search(query, filters = ipni_filter.specific) # so we don't get a mess with infraspecific names
        #res = ipni.search(query, filters=Filters.species)  # , filters = [Filters.accepted])
    try:
        for r in res:
            #print(r)
            if 'name' in r:
                r['name']
        ipni_pubYr = r['publicationYear']
        ipni_no = 'https://ipni.org/n/' + r['url']
        ipni_author = r['authors']
        #print(ipni_pubYr)
        #logging.debug('IPNI publication year found.')
    except:
        ipni_pubYr = pd.NA

    return ipni_pubYr, ipni_no, ipni_author




def exp_run_ipni(exp_data):
        """
        wrapper for swifter apply of above function 'expert_ipni()'
        """
        print(exp_data.columns)
        exp_data[['ipni_species_author', 'ipni_no', 'ipni_pub']] = exp_data.swifter.apply(lambda row: expert_ipni(row['accepted_name']), axis = 1, result_type='expand')

        return exp_data



def deduplicate_small_experts_NOBARCODE(master_db, exp_dat, verbose=True):
    """
    integrate expert determinations into master database, using expert dets with only collector name and number.
    may include coordinate
    may include species name
         but needs at least one of these
    """


    #----------------------- Imperative Values. Missing is not allowed ----------------------#
    if exp_dat.loc[['recorded_by', 'colnum', 'det_by', 'det_year']].isna().any() == True:
        # make a visible error message and raise exception (abort)
        print('\n#--> Something is WRONG here:\n',
                '\n#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#\n',
                exp_dat.loc[['recorded_by', 'colnum', 'det_by', 'det_year']],
                '\n#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#\n',
                '\n I am aborting the program. Please carefully check your input data.\n',
                '\n#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#\n',)
        raise(Exception('One of \'recorded_by\', \'colnum\', \'det_by\', or \'det_year\' is NA.\n',
                        'I do not allow such records as expert data....'))
    

    # no exception, continue
    master_db['database_from'] = 'MASTER'
    exp_dat['database_from'] ='EXPERT' 
    # concatenate
    occs = pd.concat([master_db, exp_dat])
    # find duplicates
    occs_dup = occs[occs.duplicated(subset=['recorded_by', 'colnum','suffix', 'prefix' ], keep=False)]
    occs_nondup = occs.drop_duplicates(subset=['recorded_by', 'colnum', 'suffix', 'prefix'], keep=False)

    # deduplicate the matched duplicates
    occs_dup = occs_dup.sort_value(['recorced_by', 'colnum', 'database_from'], ascending = [True, True, True])

    # test if we have a determination, coordinates or both
    if exp_dat.loc['accepted_name'].notna().all() == True: #   .isna().any() == True:
        print('EXPERT WITH ACCEPTED_NAME')
        if exp_dat['ddlat'].notna().any():
            print('ACCEPTED_NAME and COORDINATES')
            experts_merged = occs_dup.groupby(['recorded_by', 'colnum','suffix', 'prefix'], as_index = False).agg(
                            scientific_name = pd.NamedAgg(column = 'scientific_name', aggfunc = 'last'),
                            genus = pd.NamedAgg(column = 'genus', aggfunc =  'last'),
                            specific_epithet = pd.NamedAgg(column = 'specific_epithet', aggfunc = 'last' ),
                            species_author = pd.NamedAgg(column = 'species_author', aggfunc = 'last' ),
                            collector_id = pd.NamedAgg(column = 'collector_id', aggfunc = 'last' ),
                            recorded_by = pd.NamedAgg(column = 'recorded_by', aggfunc = 'last' ),
                            colnum_full = pd.NamedAgg(column = 'colnum_full', aggfunc=lambda x: ', '.join(x)),
                            prefix = pd.NamedAgg(column = 'prefix', aggfunc = 'first' ),
                            colnum = pd.NamedAgg(column = 'colnum', aggfunc = 'first' ),
                            sufix = pd.NamedAgg(column = 'sufix', aggfunc =  'first'),
                            col_date = pd.NamedAgg(column = 'col_date', aggfunc = 'last' ),
                            col_day = pd.NamedAgg(column = 'col_day', aggfunc = 'last' ),
                            col_month = pd.NamedAgg(column = 'col_month', aggfunc = 'last' ),
                            col_year = pd.NamedAgg(column = 'col_year', aggfunc = 'last' ),
                            det_by = pd.NamedAgg(column = 'det_by', aggfunc = lambda x: ' / '.join(x) ),
                            det_date = pd.NamedAgg(column = 'det_date', aggfunc = 'first' ),
                            det_day = pd.NamedAgg(column = 'det_day', aggfunc = 'first' ),
                            det_month = pd.NamedAgg(column = 'det_month', aggfunc = 'first' ),
                            det_year = pd.NamedAgg(column = 'det_year', aggfunc = 'first' ),
                            country_iso3 = pd.NamedAgg(column = 'country_iso3', aggfunc = 'last' ),
                            country = pd.NamedAgg(column = 'country', aggfunc = 'last' ),
                            continent = pd.NamedAgg(column = 'continent', aggfunc = 'last' ),
                            locality = pd.NamedAgg(column = 'locality', aggfunc = 'last' ),
                            coordinate_id = pd.NamedAgg(column = 'coordinate_id', aggfunc = 'last' ),
                            ddlong = pd.NamedAgg(column = 'ddlong', aggfunc = 'first' ),
                            ddlat = pd.NamedAgg(column = 'ddlat', aggfunc = 'first' ),
                            institute = pd.NamedAgg(column = 'institute',aggfunc = 'last'),
                            herbarium_code = pd.NamedAgg(column = 'herbarium_code', aggfunc = 'last'),
                            barcode = pd.NamedAgg(column = 'barcode', aggfunc='last'), # as we have premerged all barcodes above, it doesn't matter which one we take
                            orig_bc = pd.NamedAgg(column = 'orig_bc',aggfunc = 'last'),
                            coll_surname = pd.NamedAgg(column = 'coll_surname', aggfunc = 'last'),
                            huh_name = pd.NamedAgg(column = 'huh_name', aggfunc = 'last'),
                            geo_col = pd.NamedAgg(column = 'geo_col', aggfunc = 'last'),
                            source_id = pd.NamedAgg(column = 'source_id',  aggfunc = 'last'),
                            wiki_url = pd.NamedAgg(column = 'wiki_url', aggfunc = 'last'),
                            expert_det = pd.NamedAgg(column = 'expert_det', aggfunc =lambda x: 'SMALLEXP'),
                            status = pd.NamedAgg(column = 'status',  aggfunc = 'last'),
                            accepted_name = pd.NamedAgg(column = 'accepted_name', aggfunc = 'first'),
                            ipni_no =  pd.NamedAgg(column = 'ipni_no', aggfunc = 'last'),
                            link =  pd.NamedAgg(column = 'link',  aggfunc = 'last'),
                            ipni_species_author =  pd.NamedAgg(column = 'ipni_species_author', aggfunc = 'last')
                            )
        else:
            print('ACCEPTED_NAME but no coordinates')
            experts_merged = occs_dup.groupby(['recorded_by', 'colnum','suffix', 'prefix'], as_index = False).agg(
                            scientific_name = pd.NamedAgg(column = 'scientific_name', aggfunc = 'last'),
                            genus = pd.NamedAgg(column = 'genus', aggfunc =  'last'),
                            specific_epithet = pd.NamedAgg(column = 'specific_epithet', aggfunc = 'last' ),
                            species_author = pd.NamedAgg(column = 'species_author', aggfunc = 'last' ),
                            collector_id = pd.NamedAgg(column = 'collector_id', aggfunc = 'last' ),
                            recorded_by = pd.NamedAgg(column = 'recorded_by', aggfunc = 'last' ),
                            colnum_full = pd.NamedAgg(column = 'colnum_full', aggfunc=lambda x: ', '.join(x)),
                            prefix = pd.NamedAgg(column = 'prefix', aggfunc = 'first' ),
                            colnum = pd.NamedAgg(column = 'colnum', aggfunc = 'first' ),
                            sufix = pd.NamedAgg(column = 'sufix', aggfunc =  'first'),
                            col_date = pd.NamedAgg(column = 'col_date', aggfunc = 'last' ),
                            col_day = pd.NamedAgg(column = 'col_day', aggfunc = 'last' ),
                            col_month = pd.NamedAgg(column = 'col_month', aggfunc = 'last' ),
                            col_year = pd.NamedAgg(column = 'col_year', aggfunc = 'last' ),
                            det_by = pd.NamedAgg(column = 'det_by', aggfunc = lambda x: ' / '.join(x) ),
                            det_date = pd.NamedAgg(column = 'det_date', aggfunc = 'first' ),
                            det_day = pd.NamedAgg(column = 'det_day', aggfunc = 'first' ),
                            det_month = pd.NamedAgg(column = 'det_month', aggfunc = 'first' ),
                            det_year = pd.NamedAgg(column = 'det_year', aggfunc = 'first' ),
                            country_iso3 = pd.NamedAgg(column = 'country_iso3', aggfunc = 'last' ),
                            country = pd.NamedAgg(column = 'country', aggfunc = 'last' ),
                            continent = pd.NamedAgg(column = 'continent', aggfunc = 'last' ),
                            locality = pd.NamedAgg(column = 'locality', aggfunc = 'last' ),
                            coordinate_id = pd.NamedAgg(column = 'coordinate_id', aggfunc = 'last' ),
                            ddlong = pd.NamedAgg(column = 'ddlong', aggfunc = 'last' ),
                            ddlat = pd.NamedAgg(column = 'ddlat', aggfunc = 'last' ),
                            institute = pd.NamedAgg(column = 'institute', aggfunc = 'last'),
                            herbarium_code = pd.NamedAgg(column = 'herbarium_code', aggfunc = 'last'),
                            barcode = pd.NamedAgg(column = 'barcode', aggfunc='last'), # as we have premerged all barcodes above, it doesn't matter which one we take
                            orig_bc = pd.NamedAgg(column = 'orig_bc', aggfunc = 'last'),
                            coll_surname = pd.NamedAgg(column = 'coll_surname', aggfunc = 'last'),
                            huh_name = pd.NamedAgg(column = 'huh_name', aggfunc = 'last'),
                            geo_col = pd.NamedAgg(column = 'geo_col', aggfunc = 'last'),
                            source_id = pd.NamedAgg(column = 'source_id',  aggfunc = 'last'),
                            wiki_url = pd.NamedAgg(column = 'wiki_url', aggfunc = 'last'),
                            expert_det = pd.NamedAgg(column = 'expert_det', aggfunc =lambda x: 'SMALLEXP'),
                            status = pd.NamedAgg(column = 'status',  aggfunc = 'last'),
                            accepted_name = pd.NamedAgg(column = 'accepted_name', aggfunc = 'first'),
                            ipni_no =  pd.NamedAgg(column = 'ipni_no', aggfunc = 'last'),
                            link =  pd.NamedAgg(column = 'link',  aggfunc = 'last'),
                            ipni_species_author =  pd.NamedAgg(column = 'ipni_species_author', aggfunc = 'last')
                            )

    elif exp_dat['ddlat'].notna().any():
        print('EXPERT WITH COORDINATES but no accepted_name')

        experts_merged = occs_dup.groupby(['recorded_by', 'colnum','suffix', 'prefix'], as_index = False).agg(
                        scientific_name = pd.NamedAgg(column = 'scientific_name', aggfunc = 'last'),
                        genus = pd.NamedAgg(column = 'genus', aggfunc =  'last'),
                        specific_epithet = pd.NamedAgg(column = 'specific_epithet', aggfunc = 'last' ),
                        species_author = pd.NamedAgg(column = 'species_author', aggfunc = 'last' ),
                        collector_id = pd.NamedAgg(column = 'collector_id', aggfunc = 'last' ),
                        recorded_by = pd.NamedAgg(column = 'recorded_by', aggfunc = 'last' ),
                        colnum_full = pd.NamedAgg(column = 'colnum_full', aggfunc=lambda x: ', '.join(x)),
                        prefix = pd.NamedAgg(column = 'prefix', aggfunc = 'first' ),
                        colnum = pd.NamedAgg(column = 'colnum', aggfunc = 'first' ),
                        sufix = pd.NamedAgg(column = 'sufix', aggfunc =  'first'),
                        col_date = pd.NamedAgg(column = 'col_date', aggfunc = 'last' ),
                        col_day = pd.NamedAgg(column = 'col_day', aggfunc = 'last' ),
                        col_month = pd.NamedAgg(column = 'col_month', aggfunc = 'last' ),
                        col_year = pd.NamedAgg(column = 'col_year', aggfunc = 'last' ),
                        det_by = pd.NamedAgg(column = 'det_by', aggfunc = lambda x: ' / '.join(x) ),
                        det_date = pd.NamedAgg(column = 'det_date', aggfunc = 'first' ),
                        det_day = pd.NamedAgg(column = 'det_day', aggfunc = 'first' ),
                        det_month = pd.NamedAgg(column = 'det_month', aggfunc = 'first' ),
                        det_year = pd.NamedAgg(column = 'det_year', aggfunc = 'first' ),
                        country_iso3 = pd.NamedAgg(column = 'country_iso3', aggfunc = 'last' ),
                        country = pd.NamedAgg(column = 'country', aggfunc = 'last' ),
                        continent = pd.NamedAgg(column = 'continent', aggfunc = 'last' ),
                        locality = pd.NamedAgg(column = 'locality', aggfunc = 'last' ),
                        coordinate_id = pd.NamedAgg(column = 'coordinate_id', aggfunc = 'last' ),
                        ddlong = pd.NamedAgg(column = 'ddlong', aggfunc = 'first' ),
                        ddlat = pd.NamedAgg(column = 'ddlat', aggfunc = 'first' ),
                        institute = pd.NamedAgg(column = 'institute', aggfunc = 'last'),
                        herbarium_code = pd.NamedAgg(column = 'herbarium_code', aggfunc =  'last'),
                        barcode = pd.NamedAgg(column = 'barcode', aggfunc='last'), # as we have premerged all barcodes above, it doesn't matter which one we take
                        orig_bc = pd.NamedAgg(column = 'orig_bc', aggfunc= 'last'),
                        coll_surname = pd.NamedAgg(column = 'coll_surname', aggfunc = 'last'),
                        huh_name = pd.NamedAgg(column = 'huh_name', aggfunc = 'last'),
                        geo_col = pd.NamedAgg(column = 'geo_col', aggfunc = 'last'),
                        source_id = pd.NamedAgg(column = 'source_id', aggfunc = 'last'),
                        wiki_url = pd.NamedAgg(column = 'wiki_url', aggfunc = 'last'),
                        expert_det = pd.NamedAgg(column = 'expert_det', aggfunc = 'last'),
                        status = pd.NamedAgg(column = 'status',  aggfunc = 'last'),
                        accepted_name = pd.NamedAgg(column = 'accepted_name', aggfunc = 'last'),
                        ipni_no =  pd.NamedAgg(column = 'ipni_no', aggfunc = 'last'),
                        link =  pd.NamedAgg(column = 'link',  aggfunc= 'last'),
                        ipni_species_author =  pd.NamedAgg(column = 'ipni_species_author', aggfunc = 'last')
                        )
    else:
        print('noting to integrate as both accepted_name and coordinates are recognised as NA!!')

    experts_merged # is the merged data!

    # retreive EXP data that did not match anything and return to user for 
    no_match = occs_nondup[occs_nondup.database_from == 'EXPERT']

    occs_nondup = occs_nondup[occs_nondup.database_from == 'MASTER']

    master_updated = pd.concat([occs_nondup, experts_merged])


    ### do some final integration stats
    print('# INTEGRATION OF EXPERT DATA FINISHED\n')
    print('Of the', len(exp_dat), 'expert records,', len(exp_dat) - len(no_match), 'could be integrated.' )
    print('####################################')
    print('Master is of size: ', len(master_updated))

    return master_updated, no_match




#     # otherwise the crucial data is here so we can proceed...
#                     master_db.loc[sel_sum, 'barcode'] = new
#                     master_db.loc[sel_sum, 'accepted_name'] = exp_dat.at[i, 'accepted_name'] 
#                     master_db.loc[sel_sum, 'det_by'] = exp_dat.at[i, 'det_by'] 
#                     master_db.loc[sel_sum, 'det_year'] = exp_dat.at[i, 'det_year'] 
                    
#                     #----------------------- Facultative Values. Missing is allowed --------------------------#
#                     if ~np.isnan(exp_dat.loc[i, 'ddlat']):
#                         master_db.loc[sel_sum, 'ddlat'] = exp_dat.at[i, 'ddlat'] 
#                     if ~np.isnan(exp_dat.loc[i, 'ddlong']):
#                         master_db.loc[sel_sum, 'ddlong'] = exp_dat.at[i, 'ddlong'] 

#                     #----------------------- Automatic Values. Filled anyway --------------------------#
#                     master_db.loc[sel_sum, 'status'] = 'ACCEPTED'
#                     master_db.loc[sel_sum, 'expert_det'] = 'A_expert_det_file'
#                     master_db.loc[sel_sum, 'prefix'] = exp_dat.at[i, 'prefix'] 

#                     #----------------------- Cosmetic Values. Missing is allowed --------------------------#
#                     # print((pd.Series(exp_dat.loc[i, 'colnum_full']).isin(['-9999','NA','<NA>','NaN'])).any())
#                     # print('CNF', exp_dat.loc[i, 'colnum_full'])
#                     if pd.Series(exp_dat.loc[i, 'colnum_full']).isna().any():
#                         print('yes NA')
#                         master_db.loc[sel_sum, 'colnum_full'] = exp_dat.at[i, 'colnum_full'] 
#                     if pd.Series(exp_dat.loc[i, 'locality']).isna().any():
#                         master_db.loc[sel_sum, 'locality'] = exp_dat.at[i, 'locality'] 

#                     exp_dat.loc[i, 'matched'] = 'FILLED'








# # # # # # # # --- DEBUGGING LINES ----- # # # # # # # 

# # # debug_master = pd.read_csv('/Users/serafin/Sync/1_Annonaceae/G_GLOBAL_distr_DB/X_GLOBAL/debug/smallexp_debug.csv', sep =';')
# # debug_exp_file = '/Users/serafin/Sync/1_Annonaceae/G_GLOBAL_distr_DB/X_GLOBAL/debug/exp.csv'

# # # print(debug_exp_file)
# # # print(debug_master)
# # # print('---WORKING---')
# # debug_exp = read_expert(debug_exp_file)
# # print(debug_exp)

# # # print(debug_exp)
# # debug_exp = exp_run_ipni(debug_exp)

# # print(debug_exp)
# # # final, exception = deduplicate_experts_minimal(debug_master, debug_exp)

# # # print(final.accepted_name)
# # # print('EXCEPTIONS', exception)
# # test_Y, test_N, testA = expert_ipni(spec)
# # spec = 'Cananga odorata'
#     # print(test_Y, test_N, testA)