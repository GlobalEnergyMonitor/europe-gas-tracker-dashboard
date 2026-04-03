import os
import pandas
import numpy
import geopandas
import shapely

import dash
import plotly.express as px
#import jupyter_dash
import dash_bootstrap_components as dbc

# ****************************************
# import pipelines data
# ****************************************

# DEV MODE: load from local Excel files when GDRIVE_API_CREDENTIALS is not set
_LOCAL_PIPELINES_XLSX = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gem',
    'Copy of Pipelines (Gas_Oil_NGL) - main - for Q1 2025 EGT release.xlsx')
_LOCAL_TERMINALS_XLSX = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gem',
    'Copy of LNG Terminals - main - for 2025 Q1 EGT release.xlsx')

if os.environ.get('GDRIVE_API_CREDENTIALS'):
    import pygsheets
    gc = pygsheets.authorize(service_account_env_var='GDRIVE_API_CREDENTIALS')

    #spreadsheet = gc.open_by_key('1MX_6I2QW07lFFWMO-k3mjthBlQGFlv5aTMBmvbliYUY') # current version
    #spreadsheet = gc.open_by_key('1PKsCoVnfnCEalDBOF0Fmny0-pg1qy86DoReNHI-97WM') # Mar 2023 release
    spreadsheet = gc.open_by_key('1CktxlI1RgYUvKtL0iaNjnZszXFVjSj0JKgPnxkbm414') # Jan 2025 release

    gas_pipes = spreadsheet.worksheet('title', 'Gas pipelines').get_as_df(start='A3')
    oil_pipes = spreadsheet.worksheet('title', 'Oil/NGL pipelines').get_as_df(start='A3')
    country_ratios_df = spreadsheet.worksheet('title', 'Country ratios by pipeline').get_as_df()
    region_df_orig = spreadsheet.worksheet('title', 'Country dictionary').get_as_df(start='A2')

    spreadsheet = gc.open_by_key('1fziNYGHLG1uXozfNI6MGzwyUQt6R3-30PPfug6ZqcAk') # Jan 2025 release
    terms_df_orig = spreadsheet.worksheet('title', 'Terminals').get_as_df(start='A3')
else:
    # DEV MODE: load from pre-converted CSVs (run convert_to_dev_csv.py to regenerate)
    # Original xlsx paths kept for reference:
    #   gas_pipes = pandas.read_excel(_LOCAL_PIPELINES_XLSX, sheet_name='Gas pipelines', header=2)
    #   oil_pipes = pandas.read_excel(_LOCAL_PIPELINES_XLSX, sheet_name='OilNGL pipelines', header=2)
    #   country_ratios_df = pandas.read_excel(_LOCAL_PIPELINES_XLSX, sheet_name='Country ratios by pipeline')
    #   region_df_orig = pandas.read_excel(_LOCAL_PIPELINES_XLSX, sheet_name='Country dictionary', header=1)
    #   terms_df_orig = pandas.read_excel(_LOCAL_TERMINALS_XLSX, sheet_name='Terminals', header=2)
    _DEV_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dev_data')
    print('[DEV MODE] Loading data from CSVs in', _DEV_DATA)
    gas_pipes = pandas.read_csv(os.path.join(_DEV_DATA, 'gas_pipelines.csv')).fillna('')
    country_ratios_df = pandas.read_csv(os.path.join(_DEV_DATA, 'country_ratios.csv'))
    region_df_orig = pandas.read_csv(os.path.join(_DEV_DATA, 'country_dictionary.csv')).fillna('')
    terms_df_orig = pandas.read_csv(os.path.join(_DEV_DATA, 'terminals.csv'))
    # Restore empty strings for text columns so existing filters (e.g. !='') work
    for _col in ['Country','Status','FacilityType','TerminalID','FIDStatus','Fuel','Wiki']:
        terms_df_orig[_col] = terms_df_orig[_col].fillna('')

pipes_df_orig = gas_pipes.copy()#pandas.concat([oil_pipes, gas_pipes], ignore_index=True)
# remove empty cells for pipes, owners
pipes_df_orig = pipes_df_orig[pipes_df_orig['PipelineName']!='']

region_df_eu = region_df_orig.copy()[region_df_orig['EuropeanUnion']=='Yes']
region_df_egt = region_df_orig.copy()[region_df_orig['EuroGasTracker']=='Yes']
region_df_europe = region_df_orig.copy()[region_df_orig['Region']=='Europe']
region_df_touse = region_df_eu.copy()

country_list = region_df_touse.Country

# replace all -- with nans
terms_df_orig.replace('--', numpy.nan, inplace=True)
# remove oil export terminals
terms_df_orig = terms_df_orig.loc[terms_df_orig['Fuel']=='LNG']
# remove anything without a wiki page
terms_df_orig = terms_df_orig.loc[terms_df_orig['Wiki']!='']
# remove anything without latlon coords



# ****************************************
# creating figures
# ****************************************

def fig_capacity():

    terms_df_capacity_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                (terms_df_orig.Status.isin(['Construction','Proposed']))&
                                (terms_df_orig['FacilityType'].isin(['Import']))]

    # proposed
    terms_df_capacity_sum['Pre-construction'] += terms_df_region.loc[terms_df_region.Status=='Proposed'].groupby(
        'Country')['CapacityInBcm/y'].sum()
    # construction
    terms_df_capacity_sum['Construction'] += terms_df_region.loc[terms_df_region.Status=='Construction'].groupby(
        'Country')['CapacityInBcm/y'].sum()

    terms_df_capacity_sum.replace(numpy.nan,0,inplace=True)

    # reorder for descending values
    country_order = terms_df_capacity_sum.sum(axis=1).sort_values(ascending=True).index
    terms_df_capacity_sum = terms_df_capacity_sum.reindex(country_order)

    # ****************************************

    # GEM 2026 palette: fossil reds for terminals
    bar_dark = ['#7F142A']   # Construction (deeper = more advanced)
    bar_light = ['#CA4A50']  # Pre-construction

    nbars = terms_df_capacity_sum.index.size

    fig = px.bar(terms_df_capacity_sum[['Construction','Pre-construction']],
                 color_discrete_sequence=bar_dark+bar_light,
                 orientation='h',
                 title='Capacity of planned LNG terminals')

    fig.update_layout(
        font_family='Plus Jakarta Sans',
        font_color='#3A4A50',
        bargap=0.25,
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='',
        xaxis_title='bcm/y',
        xaxis={'side':'top'},
        title_y=.97,
        title_yanchor='top',
        title={'x':0.5, 'xanchor': 'center'},

        legend_title='Click to toggle on/off',
        legend=dict(yanchor="bottom",y=.01,xanchor="right",x=.95),

        margin=dict(l=0, r=0),
    )

    fig.update_yaxes(
        dtick=1
    )

    fig.update_xaxes(
        gridcolor='#dce3e5'
    )
    
    return(fig, terms_df_capacity_sum)

def fig_length():

    pipes_df_length_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                                 (country_ratios_df.Status.isin(['construction','proposed']))]
    
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                (country_ratios_df.Status.isin(['construction','proposed']))]
    
    # proposed
    pipes_df_length_sum['Pre-construction'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='proposed'].groupby(
        'Country')['LengthMergedKmByCountry'].sum()
    # construction
    pipes_df_length_sum['Construction'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='construction'].groupby(
        'Country')['LengthMergedKmByCountry'].sum()

    pipes_df_length_sum.replace(numpy.nan,0,inplace=True)

    # reorder for descending values
    country_order = pipes_df_length_sum.sum(axis=1).sort_values(ascending=True).index
    pipes_df_length_sum = pipes_df_length_sum.reindex(country_order)

    
    # ****************************************

    # GEM 2026 palette: indigo/purple for pipelines
    bar_dark = ['#4A57A8']   # Construction (deeper = more advanced)
    bar_light = ['#9d88dd']  # Pre-construction

    nbars = pipes_df_length_sum.index.size

    fig = px.bar(pipes_df_length_sum[['Construction','Pre-construction']],
                 color_discrete_sequence=bar_dark+bar_light,
                 orientation='h',
                 title='Km of planned gas pipelines')

    fig.update_layout(
        font_family='Plus Jakarta Sans',
        font_color='#3A4A50',
        bargap=0.25,
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='',
        xaxis_title='km',
        xaxis={'side':'top'},
        title_y=.97,
        title_yanchor='top',
        title={'x':0.5, 'xanchor': 'center'},

        legend_title='Click to toggle on/off',
        legend=dict(yanchor="bottom",y=.01,xanchor="right",x=.95),

        margin=dict(l=0, r=0),
    )

    fig.update_yaxes(
        dtick=1
    )

    fig.update_xaxes(
        gridcolor='#dce3e5'
    )
    
    return(fig, pipes_df_length_sum)

def fig_fid():
    
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                    (terms_df_orig.Status.isin(['Construction','Proposed']))&
                                    (terms_df_orig['FacilityType'].isin(['Import']))]
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                (country_ratios_df.Status.isin(['construction','proposed']))]

    projects_df_fid_sum = pandas.DataFrame(0, index=country_list, columns=['Pipelines FID','Terminals FID','Pipelines pre-FID','Terminals pre-FID'])

    # Pipelines
    projects_df_fid_sum['Pipelines FID'] += country_ratios_df_region[country_ratios_df_region.FIDStatus.isin(['FID'])].groupby('Country')['LengthPerCountryFraction'].sum()
    projects_df_fid_sum['Pipelines pre-FID'] += country_ratios_df_region[country_ratios_df_region.FIDStatus.isin(['Pre-FID'])].groupby('Country')['LengthPerCountryFraction'].sum()
    # Terminals
    projects_df_fid_sum['Terminals FID'] += terms_df_region.loc[terms_df_region.FIDStatus.isin(['FID'])].groupby('Country')['TerminalID'].count()
    projects_df_fid_sum['Terminals pre-FID'] += terms_df_region.loc[terms_df_region.FIDStatus.isin(['Pre-FID'])].groupby('Country')['TerminalID'].count()

    projects_df_fid_sum.replace(numpy.nan,0,inplace=True)

    # reorder for descending values
    country_order = projects_df_fid_sum.sum(axis=1).sort_values(ascending=True).index
    projects_df_fid_sum = projects_df_fid_sum.reindex(country_order)

    # ****************************************

    # GEM 2026 palette: indigo for pipelines, fossil red for terminals
    bar_pipes_dark = ['#4A57A8']   # Pipelines FID
    bar_pipes_light = ['#9d88dd']  # Pipelines pre-FID
    bar_terms_dark = ['#7F142A']   # Terminals FID
    bar_terms_light = ['#CA4A50']  # Terminals pre-FID

    nbars = projects_df_fid_sum.index.size

    fig = px.bar(projects_df_fid_sum[['Pipelines FID','Pipelines pre-FID',
                                      'Terminals FID', 'Terminals pre-FID']],
                 color_discrete_sequence=bar_pipes_dark+bar_pipes_light+bar_terms_dark+bar_terms_light,
                 orientation='h',
                 title='Number of projects at FID or pre-FID')

    note = '<i>Note when a pipeline passes through multiple countries, it is divided into fractions that sum to 1.</i>'
    fig.add_annotation(x=0, y=-0.1,
                       xref='x domain',
                       yref='y domain',
                       text=note,
                       showarrow=False,
                       font=dict(size=12))

    fig.update_layout(
        font_family='Plus Jakarta Sans',
        font_color='#3A4A50',
        bargap=0.25,
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='',
        xaxis_title='number of projects',
        xaxis={'side':'top'},
        title_y=.97,
        title_yanchor='top',
        title={'x':0.5, 'xanchor': 'center'},

        legend_title='Click to toggle on/off',
        legend=dict(yanchor="bottom",y=0.01,xanchor="right",x=.95),

        margin=dict(l=0, r=0),
    )

    fig.update_yaxes(
        dtick=1
    )

    fig.update_xaxes(
        gridcolor='#dce3e5'
    )

    return(fig, projects_df_fid_sum)

def fig_year_counts():
    
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                    (terms_df_orig['FacilityType'].isin(['Import']))]
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                (country_ratios_df.Status.isin(['cancelled','operating']))]

    projects_df_years_sum = pandas.DataFrame(0, index=numpy.arange(1850,2025), columns=['Cancelled pipelines',
                                                                                 'Cancelled pipeline km',
                                                                                 'Cancelled terminals',
                                                                                 'Cancelled terminal capacity',
                                                                                 'Operating pipelines',
                                                                                 'Operating pipeline km',
                                                                                 'Operating terminals',
                                                                                 'Operating terminal capacity',
                                                                                 'Shelved pipelines',
                                                                                 'Shelved pipeline km',
                                                                                 'Shelved terminals',
                                                                                 'Shelved terminal capacity',
                                                                                 'Proposed pipelines',
                                                                                 'Proposed pipeline km',
                                                                                 'Proposed terminals',
                                                                                 'Proposed terminal capacity',
                                                                                 'Construction pipelines',
                                                                                 'Construction pipeline km',
                                                                                 'Construction terminals',
                                                                                 'Construction terminal capacity',
                                                                                       ])

    # Pipelines
    projects_df_years_sum['Cancelled pipelines'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='cancelled'].groupby('CancelledYear')['LengthPerCountryFraction'].sum()
    projects_df_years_sum['Cancelled pipeline km'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='cancelled'].groupby('CancelledYear')['LengthMergedKmByCountry'].sum()
    # Terminals
    projects_df_years_sum['Cancelled terminals'] += terms_df_region.loc[terms_df_region.Status=='Cancelled'].groupby('CancelledYear')['TerminalID'].count()
    projects_df_years_sum['Cancelled terminal capacity'] += terms_df_region.loc[terms_df_region.Status=='Cancelled'].groupby('CancelledYear')['CapacityInBcm/y'].count()

    # Pipelines
    projects_df_years_sum['Operating pipelines'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='operating'].groupby('StartYearEarliest')['LengthPerCountryFraction'].sum()
    projects_df_years_sum['Operating pipeline km'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='operating'].groupby('StartYearEarliest')['LengthMergedKmByCountry'].sum()
    # Terminals
    projects_df_years_sum['Operating terminals'] += terms_df_region.loc[terms_df_region.Status=='Operating'].groupby('StartYearEarliest')['TerminalID'].count()
    projects_df_years_sum['Operating terminal capacity'] += terms_df_region.loc[terms_df_region.Status=='Operating'].groupby('StartYearEarliest')['CapacityInBcm/y'].count()

    # Pipelines
    projects_df_years_sum['Shelved pipelines'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='shelved'].groupby('ShelvedYear')['LengthPerCountryFraction'].sum()
    projects_df_years_sum['Shelved pipeline km'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='shelved'].groupby('ShelvedYear')['LengthMergedKmByCountry'].sum()
    # Terminals
    projects_df_years_sum['Shelved terminals'] += terms_df_region.loc[terms_df_region.Status=='Shelved'].groupby('ShelvedYear')['TerminalID'].count()
    projects_df_years_sum['Shelved terminal capacity'] += terms_df_region.loc[terms_df_region.Status=='Shelved'].groupby('ShelvedYear')['CapacityInBcm/y'].count()

    # Pipelines
    projects_df_years_sum['Proposed pipelines'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='proposed'].groupby('ProposalYear')['LengthPerCountryFraction'].sum()
    projects_df_years_sum['Proposed pipeline km'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='proposed'].groupby('ProposalYear')['LengthMergedKmByCountry'].sum()
    # Terminals
    projects_df_years_sum['Proposed terminals'] += terms_df_region.loc[terms_df_region.Status=='Proposed'].groupby('ProposalYear')['TerminalID'].count()
    projects_df_years_sum['Proposed terminal capacity'] += terms_df_region.loc[terms_df_region.Status=='Proposed'].groupby('ProposalYear')['CapacityInBcm/y'].count()

    # Pipelines
    projects_df_years_sum['Construction pipelines'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='construction'].groupby('ConstructionYear')['LengthPerCountryFraction'].sum()
    projects_df_years_sum['Construction pipeline km'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='construction'].groupby('ConstructionYear')['LengthMergedKmByCountry'].sum()
    # Terminals
    projects_df_years_sum['Construction terminals'] += terms_df_region.loc[terms_df_region.Status=='Construction'].groupby('ConstructionYear')['TerminalID'].count()
    projects_df_years_sum['Construction terminal capacity'] += terms_df_region.loc[terms_df_region.Status=='Construction'].groupby('ConstructionYear')['CapacityInBcm/y'].count()

    # ****************************************

    # GEM 2026 palette: semantic status colors, darker=pipelines, lighter=terminals
    bar_pipes_cancelled = ['#6e8c91']     # Cancelled (retired grey, darker)
    bar_terms_cancelled = ['#dce3e5']     # Cancelled (cancelled grey, lighter)
    bar_pipes_shelved = ['#BECCCF']       # Shelved (medium grey)
    bar_terms_shelved = ['#dce3e5']       # Shelved (light grey)
    bar_pipes_operating = ['#FE4F2D']     # Operating (orange pop, pipelines)
    bar_terms_operating = ['#FF6A4D']     # Operating (lighter orange, terminals)
    bar_pipes_proposed = ['#099ED8']      # Proposed (blue, pipelines)
    bar_terms_proposed = ['#8CD3EF']      # Proposed (light blue, terminals)
    bar_pipes_construction = ['#4A57A8']  # Construction (indigo, pipelines)
    bar_terms_construction = ['#9d88dd']  # Construction (light purple, terminals)

    fig = px.bar(projects_df_years_sum[['Cancelled pipelines',
                                        'Cancelled terminals',
                                        'Shelved pipelines',
                                        'Shelved terminals',
                                        'Operating pipelines',
                                        'Operating terminals',
                                        'Construction pipelines',
                                        'Construction terminals',
                                        'Proposed pipelines',
                                        'Proposed terminals']],
                 color_discrete_sequence=bar_pipes_cancelled+bar_terms_cancelled+bar_pipes_shelved+bar_terms_shelved+\
                                            bar_pipes_operating+bar_terms_operating+bar_pipes_proposed+bar_terms_proposed+\
                                            bar_pipes_construction+bar_terms_construction,
                 title='Number of projects by status and year')

    note = '<i>Note when a pipeline passes through multiple countries, it is divided into fractions that sum to 1.</i>'
    fig.add_annotation(x=0, y=-0.1,
                       xref='x domain',
                       yref='y domain',
                       text=note,
                       showarrow=False,
                       font=dict(size=12))

    fig.update_layout(
        font_family='Plus Jakarta Sans',
        font_color='#3A4A50',
        bargap=0.25,
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='number of projects',
        xaxis_title='year',
        xaxis={'mirror':'allticks','side':'top'},
        title_y=.97,
        title_yanchor='top',
        xaxis_range=[2011.5,2025.5],
        title={'x':0.5, 'xanchor': 'center'},
        yaxis=dict(tickmode='linear',
                   tick0=0,
                   dtick=2,
                  ),

        legend_title='Click to toggle on/off',
        legend=dict(yanchor="top",y=.99,xanchor="left",x=.05),

        margin=dict(l=0, r=0),
    )

    fig.update_xaxes(
        gridcolor='#dce3e5'
    )
    
    return(fig, projects_df_years_sum)

def fig_capacity_map():

    terms_df_capacity_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                    (terms_df_orig.Status.isin(['Construction','Proposed']))&
                                    (terms_df_orig['FacilityType'].isin(['Import']))]

    # proposed
    terms_df_capacity_sum['Pre-construction'] += terms_df_region.loc[terms_df_region.Status=='Proposed'].groupby(
        'Country')['CapacityInBcm/y'].sum()
    # construction
    terms_df_capacity_sum['Construction'] += terms_df_region.loc[terms_df_region.Status=='Construction'].groupby(
        'Country')['CapacityInBcm/y'].sum()

    terms_df_capacity_sum.replace(numpy.nan,0,inplace=True)

    # create cloropleth info
    terms_df_capacity_sum['Capacity (bcm/y)'] = terms_df_capacity_sum.sum(axis=1)

    # add ISO Code for interaction with nat earth data
    terms_df_capacity_sum['ISOCode'] = ''
    for idx,row in terms_df_capacity_sum.iterrows():
        terms_df_capacity_sum.loc[idx,'ISOCode'] = region_df_orig.loc[region_df_orig['Country']==row.name,'CountryISO3166-1alpha-3'].values[0]

    # reorder for descending values
    country_order = terms_df_capacity_sum.sort_values(by='Capacity (bcm/y)', ascending=True).index #terms_df_capacity_sum.sum(axis=1).sort_values(ascending=True).index
    terms_df_capacity_sum = terms_df_capacity_sum.reindex(country_order)

    # GEM 2026 palette: fossil red sequential for terminal choropleth
    fig = px.choropleth(terms_df_capacity_sum,
                        locations=terms_df_capacity_sum['ISOCode'],
                        color='Capacity (bcm/y)',
                        color_continuous_scale=['#f6c9c6', '#CA4A50', '#7F142A'])

    note = 'Capacity of planned LNG terminals'
    fig.add_annotation(x=0.5, y=1.1,
                       xref='x domain',
                       yref='y domain',
                       text=note,
                       showarrow=False,
                       align='center',
                       font=dict(size=16))

    fig.update_geos(
        resolution=50,
        showcoastlines=False,
        landcolor=px.colors.sample_colorscale('greys', 1e-5)[0],

        showocean=True,
        oceancolor=px.colors.sample_colorscale('blues', 0.05)[0],

        projection_type='azimuthal equal area',
        center=dict(lat=50, lon=7),
        projection_rotation=dict(lon=30),
        projection_scale=5.5)

    fig.update_layout(
        font_family='Plus Jakarta Sans',
        font_color='#3A4A50',
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='',
        xaxis_title='bcm/y',
        title_yanchor='top',
        dragmode=False,

        margin=dict(l=0, r=0),)

        #coloraxis_colorbar_x=1.01)
    
    fig.update_coloraxes(
        colorbar=dict(thickness=15, title={'side':'right'}))
    fig.update_traces(
        selector=dict(type='choropleth'))
    
    return(fig)

def fig_kilometers_map():

    pipes_df_length_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                                 (country_ratios_df.Status.isin(['construction','proposed']))]

    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                (country_ratios_df.Status.isin(['construction','proposed']))]

    # proposed
    pipes_df_length_sum['Pre-construction'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='proposed'].groupby(
        'Country')['LengthMergedKmByCountry'].sum()
    # construction
    pipes_df_length_sum['Construction'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='construction'].groupby(
        'Country')['LengthMergedKmByCountry'].sum()

    pipes_df_length_sum.replace(numpy.nan,0,inplace=True)

    # reorder for descending values
    #country_order = pipes_df_length_sum.sum(axis=1).sort_values(ascending=True).index
    #pipes_df_length_sum = pipes_df_length_sum.reindex(country_order)

    # create cloropleth info
    pipes_df_length_sum['Pipelines (km)'] = pipes_df_length_sum.sum(axis=1)

    # add ISO Code for interaction with nat earth data
    pipes_df_length_sum['ISOCode'] = ''
    for idx,row in  pipes_df_length_sum.iterrows():
         pipes_df_length_sum.loc[idx,'ISOCode'] = region_df_orig.loc[region_df_orig['Country']==row.name,'CountryISO3166-1alpha-3'].values[0]

    # reorder for descending values
    country_order =  pipes_df_length_sum.sort_values(by='Pipelines (km)', ascending=True).index #pipes_df_length_sum.sum(axis=1).sort_values(ascending=True).index
    pipes_df_length_sum = pipes_df_length_sum.reindex(country_order)

    # GEM 2026 palette: purple sequential for pipeline choropleth
    fig = px.choropleth(pipes_df_length_sum,
                        locations=pipes_df_length_sum['ISOCode'],
                        color='Pipelines (km)',
                        color_continuous_scale=['#cec3ee', '#6c51bd', '#412e7a'])

    note = 'Km of planned gas pipelines'
    fig.add_annotation(x=0.5, y=1.1,
                       xref='x domain',
                       yref='y domain',
                       text=note,
                       showarrow=False,
                       align='center',
                       font=dict(size=16))

    fig.update_geos(
        resolution=50,
        showcoastlines=False,
        landcolor=px.colors.sample_colorscale('greys', 1e-5)[0],

        showocean=True,
        oceancolor=px.colors.sample_colorscale('blues', 0.05)[0],

        projection_type='azimuthal equal area',
        center=dict(lat=50, lon=7),
        projection_rotation=dict(lon=30),
        projection_scale=5.5)

    fig.update_layout(
        font_family='Plus Jakarta Sans',
        font_color='#3A4A50',
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='',
        xaxis_title='bcm/y',
        title_yanchor='top',
        dragmode=False,

        margin=dict(l=0, r=0),)

        #coloraxis_colorbar_x=1.01)
    
    fig.update_coloraxes(
        colorbar=dict(thickness=15, title={'side':'right'}))
    #fig.update_traces(
    #    selector=dict(type='choropleth'),
    #    hovertemplate='{Country}<br>{Capacity (bcm/y)} bcm/y'
    #)
    
    return(fig)

# ****************************************
# dashboard details with tab
# ****************************************

external_stylesheets = [
    dbc.themes.BOOTSTRAP,
    'https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Barlow+Semi+Condensed:wght@400;500;600&display=swap',
]
app = dash.Dash(__name__, 
                external_stylesheets=external_stylesheets,
               #meta_tags=[
               #    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
               #],
               )
app.title = "Europe Gas Tracker dashboard"
server = app.server

# ******************************
# create graphs of charts
# use dcc.Graph to create these

capacity_figure = dash.dcc.Graph(id='fig_capacity_id', 
                                 config={'displayModeBar':False},
                                 figure=fig_capacity()[0],
                                 className='h-100')
length_figure = dash.dcc.Graph(id='fig_length_id', 
                               config={'displayModeBar':False},
                               figure=fig_length()[0],
                               className='h-100')
fid_figure = dash.dcc.Graph(id='fig_fid_id', 
                               config={'displayModeBar':False},
                               figure=fig_fid()[0],
                            className='h-100')
year_counts_figure = dash.dcc.Graph(id='fig_year_counts_id',
                              config={'displayModeBar':False},
                              figure=fig_year_counts()[0],
                                    className='h-100')
map_capacity_figure = dash.dcc.Graph(id='fig_capacity_map_id',
                                     config={'displayModeBar':False},
                                     figure=fig_capacity_map(),
                                     className='h-100')
map_kilometers_figure = dash.dcc.Graph(id='fig_kilometers_map_id',
                                     config={'displayModeBar':False},
                                     figure=fig_kilometers_map(),
                                       className='h-100')

# ******************************
# define layout

# create first tab
tab1_content = dbc.Container(fluid=True, 
                             children=[
                                 dbc.Row([
                                     dbc.Col(map_capacity_figure, 
                                             align='start', 
                                             lg=6, 
                                             md=12),
                                 ], 
                                     justify='center'),
                                 dbc.Row([
                                     dbc.Col(capacity_figure, 
                                             align='start', 
                                             lg=5, 
                                             md=12,
                                             style={'height':'800px'}),
                                 ], 
                                     justify='center'),
                             ])

# create second tab
tab2_content = dbc.Container(fluid=True, 
                             children=[
                                 dbc.Row([
                                     dbc.Col(map_kilometers_figure, 
                                             align='start', 
                                             lg=6, 
                                             md=12),
                                 ], 
                                     justify='center'),
                                 dbc.Row([
                                     dbc.Col(length_figure, 
                                             align='start', 
                                             lg=5, 
                                             md=12,
                                             style={'height':'800px'}),
                                 ], 
                                     justify='center'),
                             ])

# create third tab
tab3_content = dbc.Container(fluid=True, 
                             children=[
                                 dbc.Row([
                                     dbc.Col(fid_figure, 
                                             align='start', 
                                             lg=6, 
                                             md=12,
                                             style={'height':'100%'}),
                                     dbc.Col(year_counts_figure, 
                                             align='start', 
                                             lg=6, 
                                             md=12,
                                             style={'height':'100%'})
                                 ], style={'height':'800px'})
                             ])

# put all the tabs together
tabs = dbc.Tabs([
    dbc.Tab(tab1_content, label="LNG terminals",
            label_style={"color": "#004A63", "fontFamily": "Plus Jakarta Sans"},
            active_label_style={"color": "#FE4F2D"}),
    dbc.Tab(tab2_content, label="Methane gas pipelines",
            label_style={"color": "#004A63", "fontFamily": "Plus Jakarta Sans"},
            active_label_style={"color": "#FE4F2D"}),
    dbc.Tab(tab3_content, label="FID and status changes",
            label_style={"color": "#004A63", "fontFamily": "Plus Jakarta Sans"},
            active_label_style={"color": "#FE4F2D"}),
])

# fluid=True means it will fill horiz space and resize
# https://dash-bootstrap-components.opensource.faculty.ai/docs/components/layout/
app.layout = dbc.Container([
    tabs,
],
    fluid=True)

if __name__ == '__main__':
    app.run(debug=True)

