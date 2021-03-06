import json
from flatten_json import flatten
import pandas as pd
from scipy import stats
import statistics
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import DBSCAN


# transform time series data to slope, sd and mean
def slope_sd_mean(row, n_months, n_years):
    if(n_months == 12):
        x = list(range(1, n_months*n_years+1))
        lr_res = stats.linregress(x, row[1:])
        slope = lr_res.slope
    else:
        season = list(range(1, n_months+1))
        i = 1
        slope_season = []
        while i < len(row):
            lr_season = stats.linregress(season, row[i:i+n_months])
            i += n_months
            slope_season.append(lr_season.slope)
        slope = statistics.mean(slope_season)
    
    mean = statistics.mean(row[1:])
    sd = statistics.stdev(row[1:])
    results = [row[0], slope, mean, sd]
    
    return results


def data_to_slope_sd_mean(data, n_months, n_years):
    data_list = data.values.tolist()
    data_list_result = [slope_sd_mean(elt, n_months, n_years) for elt in data_list]
    return data_list_result


def crop_str_to_arr(elt):
    elt['indicator_period']['indicator']['crop'] = json.loads(elt['indicator_period']['indicator']['crop'])
    return elt


def transform_data(data, n_months, n_years):
    indicator_prefs = data['indicator_period_indicator_pref'].unique()
    trnsformed_res = pd.DataFrame([])

    for pref in indicator_prefs:
        sub_pref = (data.groupby(['indicator_period_indicator_pref'])).get_group(pref)
        years = data['indicator_period_period'].unique()
        df_merge_years = pd.DataFrame([])
        for year in years:
            grp_year = (sub_pref.groupby(['indicator_period_period'])).get_group(year)
            cell_ids = grp_year['cellid'].unique()
            df_by_cellids = pd.DataFrame([])

            for cell_id in cell_ids:
                grp_cell = (grp_year.groupby(['cellid'])).get_group(cell_id)
                grp_cell.drop(labels=['cellid'], axis="columns", inplace=True)
                out = grp_cell.set_index(['indicator_period_period','indicator_period_indicator_pref']).stack()
                out.index = out.index.map('_'.join)
                result = out.to_frame().T
                result.insert(loc=0, column='cellid', value=cell_id)
                df_by_cellids = df_by_cellids.append(result)
            
            if df_merge_years.empty:
                df_merge_years = df_by_cellids
            else:
                df_merge_years = pd.merge(df_merge_years, df_by_cellids)

        res = data_to_slope_sd_mean(df_merge_years, n_months, n_years)
        df = pd.DataFrame(res, columns=['cellid','slope_'+pref,'mean_'+pref, 'sd_'+pref])
    
        if trnsformed_res.empty:
            trnsformed_res = df
        else:
            trnsformed_res = pd.merge(trnsformed_res, df)

    return trnsformed_res


def dbscan_analysis(data, n_months, n_years, eps = 20, minPts = 10):
    #flatten data to indicators dataframe
    indicators = [crop_str_to_arr(x) for x in data['data']]
    df = pd.DataFrame([flatten(x) for x in indicators])
    df.drop(labels=['_id','indicator_period_indicator_indicator_type',
    'indicator_period__id','indicator_period_indicator__id',
    'indicator_period_indicator_name','indicator_period_indicator_crop_0__id'
    ], axis="columns", inplace=True)
    #result = pd.DataFrame([])
    #group df by crop name
    #crops = df['indicator_period_indicator_crop_0_name'].unique()
    #for crop in crops:
    #gr = (df.groupby(['indicator_period_indicator_crop_0_name'])).get_group(crop)
    df.drop(labels=['indicator_period_indicator_crop_0_name'], axis="columns", inplace=True)
    transformed_gr = transform_data(df, n_months, n_years)
    #indicators data without cellid
    ind_data = transformed_gr.iloc[: , 1:] 
    #scale indicators data
    scaled_data = pd.DataFrame(StandardScaler().fit_transform(ind_data), columns=ind_data.columns)
    #apply DBSCAN clustering
    db = DBSCAN(eps = eps, min_samples = minPts).fit(scaled_data)
    labels = db.labels_
    
    scaled_data["cluster"] = labels
    analysis_res = pd.concat([transformed_gr['cellid'], scaled_data], axis=1)

    return analysis_res