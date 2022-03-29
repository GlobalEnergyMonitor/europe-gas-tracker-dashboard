import pandas
import numpy
import pygsheets
import geopandas
import shapely

import dash
import plotly.express as px
#import jupyter_dash
import dash_bootstrap_components as dbc

# ****************************************
# import pipelines data
# ****************************************

gc = pygsheets.authorize(service_account_env_var = 'GDRIVE_API_CREDENTIALS')
spreadsheet = gc.open_by_key('1MX_6I2QW07lFFWMO-k3mjthBlQGFlv5aTMBmvbliYUY') # current version

gas_pipes = spreadsheet.worksheet('title', 'Gas pipelines').get_as_df()
oil_pipes = spreadsheet.worksheet('title', 'Oil/NGL pipelines').get_as_df()

gas_pipes = gas_pipes.drop('WKTFormat', axis=1) # delete WKTFormat column
oil_pipes = oil_pipes.drop('WKTFormat', axis=1)
pipes_df_orig = pandas.concat([oil_pipes, gas_pipes], ignore_index=True)
# remove empty cells for pipes, owners
pipes_df_orig = pipes_df_orig[pipes_df_orig['PipelineName']!='']

#get other relevant sheets
country_ratios_df = spreadsheet.worksheet('title', 'Country ratios by pipeline').get_as_df()

# ****************************************
# special cases
# ****************************************
# as of Feb 22, Nord Stream 2 is "Idle" in our data but should probably be "Construction"...

# force Nigeria-Morocco Pipeline to be Proposed (instead of Construction)
country_ratios_df.loc[country_ratios_df.PipelineName=='Nord Stream 2', 'Status'] = 'Construction'
pipes_df_orig.loc[pipes_df_orig.PipelineName=='Nord Stream 2', 'Status'] = 'Construction'

country_ratios_df.replace('--', numpy.nan, inplace=True)
pipes_df_orig.replace('--', numpy.nan, inplace=True)

# https://www.gem.wiki/Poland-Ukraine_Interconnector_Gas_Pipeline
# our country_ratios code calculates this is half in each country, but it's not
country_ratios_df.loc[(country_ratios_df.PipelineName=='Poland-Ukraine Interconnector Gas Pipeline')& \
    (country_ratios_df.Country=='Poland'),'LengthKnownKmByCountry'] = 1.5

country_ratios_df.loc[(country_ratios_df.PipelineName=='Poland-Ukraine Interconnector Gas Pipeline')& \
    (country_ratios_df.Country=='Ukraine'),'LengthKnownKmByCountry'] = 99.0

# ****************************************
# convert routes to geometry objects
# ****************************************

def convert_gfit_to_linestring(coord_str, pipeline_name):
    '''
    Takes string from GFIT column of coordinates for a single pipeline,
    converts that string into Shapely LineString or MultiLinestring.
    '''
    #print(coord_str, pipeline_name)
    if ':' in coord_str and ';' not in coord_str:
        # simple geometry; no branching
        # create nested list of lists, separating on colons        
        coord_list = coord_str.split(':')
        coord_list_tuples = []
        # non-branched pipeline (nested list with one level)
        # convert nested list of lists to list of tuples
        try:
            for element in coord_list:
                element_tuple = (float(element.split(',')[1]), 
                                 float(element.split(',')[0]))
                coord_list_tuples.append(element_tuple)
        except:
            print(f"Exception for {pipeline_name}; element: {element}") # for db
        route_conv = shapely.geometry.LineString(coord_list_tuples)

    elif ':' in coord_str and ';' in coord_str:
        # create a nested list of lists, separating on semicolons
        coord_list = coord_str.split(';')   
        # create a second level of nesting, separating on colons
        coord_list = [x.split(':') for x in coord_list]
        # branched pipeline (nested list with two levels)
        route_conv_list_all = []
        
        for nested_list in coord_list:
            coord_list_tuples = []
            # process element
            try:
                for element in nested_list:
                    element_tuple = (float(element.split(',')[1]), 
                                     float(element.split(',')[0]))
                    coord_list_tuples.append(element_tuple)
            except:
                print(f"Exception for {pipeline_name}; element: {element}") # for db
            # process coord_list_tuples
            try:
                route_conv_list = shapely.geometry.LineString(coord_list_tuples)
                route_conv_list_all.append(route_conv_list)
            except:
                print(f"Exception for {pipeline_name}; coord_list_tuples: {coord_list_tuples}") # for db
                pass
            
        route_conv = shapely.geometry.MultiLineString(route_conv_list_all)
        
    return route_conv

def convert_all_pipelines(df):
    """
    Apply the conversion function to all pipelines in the dataframe.
    """
    # create geometry column with empty strings
    #df.assign(ColName='geometry', dtype='str')
    df['geometry'] = ''
    #print(df['geometry'])
    
    # filter to keep only pipelines with routes
    mask_route = df['Route'].str.contains(',' or ':')
    pipes_with_route = df.loc[mask_route]
    
    for row in pipes_with_route.index:
        route_str = df.at[row, 'Route']
        pipeline_name = df.at[row, 'PipelineName']
        
        route_str_converted = convert_gfit_to_linestring(route_str, pipeline_name)
    
        #print(df.at[row,'ProjectID'])
        #print(pipeline_name)
        #print(route_str_converted)
        
        df.at[row, 'geometry'] = route_str_converted   
        
    return df


# code to create a dataframe with WKT formatted geometry
no_route_options = [
    'Unavailable', 
    'Capacity expansion only', 
    'Bidirectionality upgrade only',
    'Short route (< 100 km)', 
    'N/A',
    ''
]

# (1) copy, clean up
to_convert_df = pipes_df_orig.copy()
to_convert_df = to_convert_df[~to_convert_df['Route'].isin(no_route_options)]

# also keep the non-converted ones separate
not_converted_df = pipes_df_orig.copy()
not_converted_df = not_converted_df[not_converted_df['Route'].isin(no_route_options)]
# add a dummy column so that the dimensions match with converted wkt pipelines
not_converted_df.assign(ColName='geometry')
not_converted_df['geometry'] = [shapely.geometry.MultiLineString()]*not_converted_df.shape[0]
not_converted_df.reset_index(drop=True)
not_converted_gdf = geopandas.GeoDataFrame(not_converted_df, geometry=not_converted_df['geometry'])

# (2) convert all pipelines
pipes_df_wkt = convert_all_pipelines(to_convert_df)
pipes_df_wkt = pipes_df_wkt.reset_index(drop=True)

# (3) store in a GeoDataFrame, attach a projection, transform to a different one
pipes_df_wkt_gdf = geopandas.GeoDataFrame(pipes_df_wkt, geometry=pipes_df_wkt['geometry'])
pipes_df_wkt_gdf = pipes_df_wkt_gdf.set_crs('epsg:4326')
pipes_df_wkt_gdf_4087 = pipes_df_wkt_gdf.to_crs('epsg:4087')

pipes_df_converted_routes = pandas.concat([pipes_df_wkt_gdf, not_converted_gdf])
pipes_df_converted_routes = pipes_df_converted_routes.reset_index(drop=True)
pipes_df_converted_routes.sort_values('ProjectID', inplace=True)

pipes_gdf = geopandas.GeoDataFrame(pipes_df_converted_routes, geometry=pipes_df_converted_routes['geometry'])

# ****************************************
# import terminals
# ****************************************

spreadsheet = gc.open_by_key('1nQChDxZXBaHX53alSXfD0IHpHdxpUSjMALEaR_JNFXE')

terms_df_orig = spreadsheet.worksheet('title', 'Terminals').get_as_df()

# replace all -- with nans
terms_df_orig.replace('--', numpy.nan, inplace=True)
# remove oil export terminals
terms_df_orig = terms_df_orig.loc[terms_df_orig['Type1']!='Oil']
# remove anything without a wiki page
terms_df_orig = terms_df_orig.loc[terms_df_orig['Wiki']!='']
# remove anything without latlon coords


region_df_orig = spreadsheet.worksheet('title', 'Region dictionary').get_as_df()

region_df_eu = region_df_orig.copy()[region_df_orig['EuropeanUnion']=='Yes']
region_df_egt = region_df_orig.copy()[region_df_orig['EuroGasTracker']=='Yes']
region_df_europe = region_df_orig.copy()[region_df_orig['Region']=='Europe']
region_df_touse = region_df_eu.copy()

country_list = region_df_touse.Country

# ****************************************
# convert lat/lon geometry objects
# ****************************************

# code to create a dataframe with WKT formatted geometry
no_lonlat_options = [
    'Unknown',
    'TBD'
]

# (1) copy, clean up
to_convert_df = terms_df_orig.copy()
to_convert_df = to_convert_df[~(to_convert_df['Latitude'].isin(no_lonlat_options)) |
                             ~(to_convert_df['Longitude'].isin(no_lonlat_options))]

# also keep the non-converted ones separate
not_converted_df = terms_df_orig.copy()
not_converted_df = not_converted_df[(not_converted_df['Longitude'].isin(no_lonlat_options)) | 
                                    (not_converted_df['Latitude'].isin(no_lonlat_options))]
# add a dummy column so that the dimensions match with converted wkt pipelines
not_converted_df.assign(ColName='geometry')
not_converted_df['geometry'] = [shapely.geometry.Point()]*not_converted_df.shape[0]
not_converted_df.reset_index(drop=True)
not_converted_gdf = geopandas.GeoDataFrame(not_converted_df, geometry=not_converted_df['geometry'])

# (2) convert all terminals
terms_df_converted = to_convert_df.copy()
terms_df_converted.assign(ColName='geometry')
terms_df_converted['geometry'] = to_convert_df[['Longitude','Latitude']].apply(shapely.geometry.Point, axis=1)
terms_df_converted = terms_df_converted.reset_index(drop=True)

# # (3) store in a GeoDataFrame, attach a projection, transform to a different one
terms_df_gdf = geopandas.GeoDataFrame(terms_df_converted, geometry=terms_df_converted['geometry'])
terms_df_gdf = terms_df_gdf.set_crs('epsg:4326')
terms_df_gdf_4087 = terms_df_gdf.to_crs('epsg:4087')

terms_df_converted_locations = pandas.concat([terms_df_gdf, not_converted_gdf])
terms_df_converted_locations = terms_df_converted_locations.reset_index(drop=True)
terms_df_converted_locations.sort_values('ComboID', inplace=True)

terms_gdf = geopandas.GeoDataFrame(terms_df_converted_locations, geometry=terms_df_converted_locations['geometry'])
terms_gdf_region = terms_gdf.loc[terms_gdf['Country'].isin(region_df_touse.Country)]

# ****************************************
# creating figures
# ****************************************

def fig_capacity():

    terms_df_capacity_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                    (terms_df_orig.Status.isin(['Construction','Proposed']))&
                                    (terms_df_orig.Facility.isin(['Import']))]

    # proposed
    terms_df_capacity_sum['Pre-construction'] += terms_df_region.loc[terms_df_region.Status=='Proposed'].groupby(
        'Country')['CapacityInBcm/y'].sum()
    # construction
    terms_df_capacity_sum['Construction'] += terms_df_region.loc[terms_df_region.Status=='Construction'].groupby(
        'Country')['CapacityInBcm/y'].sum()

    terms_df_capacity_sum.replace(numpy.nan,0,inplace=True)
# ****************************************
# creating figures
# ****************************************

def fig_capacity():

    terms_df_capacity_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                    (terms_df_orig.Status.isin(['Construction','Proposed']))&
                                    (terms_df_orig.Facility.isin(['Import']))]

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

    colorscale_touse = 'ylorbr'

    bar_dark = px.colors.sample_colorscale(colorscale_touse, 0.9)
    bar_light = px.colors.sample_colorscale(colorscale_touse, 0.6)

    nbars = terms_df_capacity_sum.index.size

    fig = px.bar(terms_df_capacity_sum[['Construction','Pre-construction']], 
                 color_discrete_sequence=bar_dark+bar_light, 
                 orientation='h', height=800,
                 title='Capacity of planned LNG terminals')

    fig.update_layout(
        font_family='Helvetica',
        font_color=px.colors.sample_colorscale('greys', 0.5)[0],
        bargap=0.25,
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='country',
        xaxis_title='bcm/y',
        xaxis={'side':'top'},
        title_y=.97,
        title_yanchor='top',

        legend_title=None,
        #legend=dict(yanchor="bottom",y=0.01,xanchor="right",x=0.99,bgcolor='rgba(0,0,0,0)'),
        legend=dict(yanchor="top",y=1,xanchor="left",x=1.01,bgcolor='rgba(0,0,0,0)'),
    )

    fig.update_yaxes(
        dtick=1
    )

    fig.update_xaxes(
        gridcolor=px.colors.sample_colorscale('greys', 0.25)[0]
    )
    
    return(fig)

def fig_length():

    pipes_df_length_sum = pandas.DataFrame(0, index=country_list, columns=['Pre-construction','Construction'])
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                                 (country_ratios_df.Status.isin(['Construction','Proposed']))]
    
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                (country_ratios_df.Status.isin(['Construction','Proposed']))]
    
    # proposed
    pipes_df_length_sum['Pre-construction'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='Proposed'].groupby(
        'Country')['MergedKmByCountry'].sum()
    # construction
    pipes_df_length_sum['Construction'] += country_ratios_df_region.loc[country_ratios_df_region.Status=='Construction'].groupby(
        'Country')['MergedKmByCountry'].sum()

    pipes_df_length_sum.replace(numpy.nan,0,inplace=True)

    # reorder for descending values
    country_order = pipes_df_length_sum.sum(axis=1).sort_values(ascending=True).index
    pipes_df_length_sum = pipes_df_length_sum.reindex(country_order)

    
    # ****************************************

    colorscale_touse = 'greens'

    bar_dark = px.colors.sample_colorscale(colorscale_touse, 0.9)
    bar_light = px.colors.sample_colorscale(colorscale_touse, 0.6)

    nbars = pipes_df_length_sum.index.size

    fig = px.bar(pipes_df_length_sum[['Construction','Pre-construction']], 
                 color_discrete_sequence=bar_dark+bar_light, 
                 orientation='h', height=800,
                 title='Kilometers of planned gas pipelines')

    fig.update_layout(
        font_family='Helvetica',
        font_color=px.colors.sample_colorscale('greys', 0.5)[0],
        bargap=0.25, 
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='country',
        xaxis_title='km',
        xaxis={'side':'top'},
        title_y=.97,
        title_yanchor='top',

        legend_title=None,
        #legend=dict(yanchor="bottom",y=0.01,xanchor="right",x=0.99,bgcolor='rgba(0,0,0,0)'),
        legend=dict(yanchor="top",y=1,xanchor="left",x=1.01,bgcolor='rgba(0,0,0,0)'),
    )

    fig.update_yaxes(
        dtick=1
    )

    fig.update_xaxes(
        gridcolor=px.colors.sample_colorscale('greys', 0.25)[0]
    )
    
    return(fig)

def fig_fid():
    
    terms_df_region = terms_df_orig[(terms_df_orig.Country.isin(region_df_touse.Country))&
                                    (terms_df_orig.Status.isin(['Construction','Proposed']))&
                                    (terms_df_orig.Facility.isin(['Import']))]
    country_ratios_df_region = country_ratios_df[(country_ratios_df.Country.isin(region_df_touse.Country))&
                                (country_ratios_df.Status.isin(['Construction','Proposed']))]

    projects_df_fid_sum = pandas.DataFrame(0, index=country_list, columns=['Pipelines FID','Terminals FID','Pipelines pre-FID','Terminals pre-FID'])

    # Pipelines
    projects_df_fid_sum['Pipelines FID'] += country_ratios_df_region[country_ratios_df_region.FID.isin(['FID'])].groupby('Country')['LengthPerCountryFraction'].sum()
    projects_df_fid_sum['Pipelines pre-FID'] += country_ratios_df_region[country_ratios_df_region.FID.isin(['Pre-FID'])].groupby('Country')['LengthPerCountryFraction'].sum()
    # Terminals
    projects_df_fid_sum['Terminals FID'] += terms_df_region.loc[terms_df_region.FID.isin(['FID'])].groupby('Country')['TerminalID'].count()
    projects_df_fid_sum['Terminals pre-FID'] += terms_df_region.loc[terms_df_region.FID.isin(['Pre-FID'])].groupby('Country')['TerminalID'].count()

    projects_df_fid_sum.replace(numpy.nan,0,inplace=True)

    # reorder for descending values
    country_order = projects_df_fid_sum.sum(axis=1).sort_values(ascending=True).index
    projects_df_fid_sum = projects_df_fid_sum.reindex(country_order)

    # ****************************************

    colorscale_touse = 'blues'

    bar_pipes_dark = px.colors.sample_colorscale(colorscale_touse, 0.9)
    bar_pipes_light = px.colors.sample_colorscale(colorscale_touse, 0.7)
    bar_terms_dark = px.colors.sample_colorscale(colorscale_touse, 0.5)
    bar_terms_light = px.colors.sample_colorscale(colorscale_touse, 0.3)

    nbars = projects_df_fid_sum.index.size

    fig = px.bar(projects_df_fid_sum[['Pipelines FID','Pipelines pre-FID',
                                      'Terminals FID', 'Terminals pre-FID']], 
                 color_discrete_sequence=bar_pipes_dark+bar_pipes_light+bar_terms_dark+bar_terms_light, 
                 orientation='h', height=800,
                 title='Number of projects at FID or pre-FID')

    note = '<i>Note when a pipeline passes through multiple countries, it is divided into fractions that sum to 1.</i>'
    fig.add_annotation(x=0, y=-0.1,
                       xref='x domain',
                       yref='y domain',
                       text=note,
                       showarrow=False,
                       font=dict(size=12))
    
    fig.update_layout(
        font_family='Helvetica',
        font_color=px.colors.sample_colorscale('greys', 0.5)[0],
        bargap=0.25,
        plot_bgcolor='white',
        paper_bgcolor='white',

        yaxis_title='country',
        xaxis_title='number of projects',
        xaxis={'side':'top'},
        title_y=.97,
        title_yanchor='top',

        legend_title=None,
        #legend=dict(yanchor="bottom",y=0.01,xanchor="right",x=0.99,bgcolor='rgba(0,0,0,0)'),
        legend=dict(yanchor="top",y=1,xanchor="left",x=1.01,bgcolor='rgba(0,0,0,0)'),
    )

    fig.update_yaxes(
        dtick=1
    )

    fig.update_xaxes(
        gridcolor=px.colors.sample_colorscale('greys', 0.25)[0]
    )

    return(fig)

# ****************************************
# dashboard details
# ****************************************

external_stylesheets = [dbc.themes.BOOTSTRAP]
#app = jupyter_dash.JupyterDash(__name__, external_stylesheets=external_stylesheets)
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
app.title = "Europe Gas Tracker dashboard"
server = app.server

# ******************************
# create graphs of charts

# dash_header = html.H2(children='Coal power dashboard')

capacity_figure = dash.dcc.Graph(id='fig_capacity_id', 
                                 config={'displayModeBar':False},
                                 figure=fig_capacity())
length_figure = dash.dcc.Graph(id='fig_length_id', 
                               config={'displayModeBar':False},
                               figure=fig_length())
fid_figure = dash.dcc.Graph(id='fig_fid_id', 
                               config={'displayModeBar':False},
                               figure=fig_fid())
#, config={'displayModeBar':False})


# ******************************
# define layout

# note the dash.html.Div([ up top is necessary for it to work...
app.layout = dash.html.Div([
    dbc.Container(fluid=True, children=[
    dbc.Row([
        dbc.Col(capacity_figure, style={'maxHeight':'400px', 'overflow':'scroll'}, align='start'),
        dbc.Col(length_figure, style={'maxHeight':'400px', 'overflow':'scroll'}, align='start')
    ]),
    dbc.Row(),
    dbc.Row([
        dbc.Col(fid_figure, style={'maxHeight':'400px', 'overflow':'scroll'}, align='start')])
])
])

# style={'maxHeight':'400px', 'overflow':'scroll'} - add before align='start'

#app.run_server(mode='external')
#app.run_server(mode='inline')

#@app.callback(
#    dash.dependencies.Output('figure_capacity', 'figure'),
#    dash.dependencies.Output('figure_length', 'figure'),
#    dash.dependencies.Output('figure_fid', 'figure'))

if __name__ == '__main__':
    app.run_server()