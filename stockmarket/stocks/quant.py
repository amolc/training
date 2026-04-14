import os
import pandas as pd
import numpy as np
from plotly.subplots import make_subplots
import requests
import math
from tvDatafeed import TvDatafeed, Interval
try:
    from telegram_notifier import TelegramNotifier
except ImportError:
    TelegramNotifier = None
from pathlib import Path
from scipy.signal import argrelextrema
import pathlib
try:
    import pygsheets
except ImportError:
    pygsheets = None
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import time
import json
from scipy.stats import linregress

try:
    from icecream import ic
except ImportError:
    ic = print

import sqlite3 as sql

try:
    import talib as ta
except ImportError:
    ta = None
from datetime import datetime




BASE_DIR = os.path.dirname(os.path.dirname(__file__))
tv = TvDatafeed()


pd.set_option("mode.chained_assignment", None)



class Quant:

    # def getdata(stock,source,interval,length):
    #     # df = {}
    #     df = pd.DataFrame()
    #     if interval == '5.0':
    #         interval=5
    #     elif interval== '3.0' :
    #         interval=3
    #     elif interval== '1.0' :
    #         interval=1
    #     elif interval== '15.0' :
    #         interval=15
    #     elif interval== '30.0' :
    #         interval=15

    #     # print(interval)
    #     df = tv.get_hist(
    #         symbol=stock,
    #         exchange=source,
    #         interval= Interval(str(interval)) ,
    #         n_bars=int(length),
    #     )
    #     #print(df.columns)
    #     try:
    #         df.reset_index(inplace=True)
    #         np.round(df, decimals=4)
    #     except:
    #         print("Issue to get data from ", stock, source )
        
    #     #print(df.info())
    #     return df
    def getdata(self, stock, source, interval, length):
        max_retries = 5
        if interval == '5.0':
            interval = 5
        elif interval == '3.0':
            interval = 3
        elif interval == '1.0':
            interval = 1
        elif interval == '15.0':
            interval = 15
        elif interval == '30.0':
            interval = 30

        df = pd.DataFrame()
        for attempt in range(1, max_retries + 1):
            print(f"Attempt {attempt} to fetch data")
            try:
                df = tv.get_hist(
                    symbol=stock,
                    exchange=source,
                    interval=Interval(str(interval)),
                    n_bars=int(length),
                )
                if df is not None and not df.empty:
                    df.reset_index(inplace=True)
                    df = np.round(df, decimals=4)
                    if not df.isnull().values.any():
                        print("Data fetched successfully")
                        return df
            except Exception as e:
                print(f"Error fetching data: {e}")
            
            time.sleep(2)
        
        return df
    
    def getdayprice(self, stock, source, days):
        max_retries = 5
        df_day = pd.DataFrame()
        for attempt in range(1, max_retries + 1):
            print(f"Day Data retry {attempt} to fetch data")
            try:
                df_day = tv.get_hist(
                    symbol=stock,
                    exchange=source,
                    interval=Interval('1H'),
                    n_bars=int(days),
                )
                if df_day is not None and not df_day.empty:
                    df_day.reset_index(inplace=True)
                    df_day = np.round(df_day, decimals=4)
                    if not df_day.isnull().values.any():
                        print("Data fetched successfully")
                        return df_day
            except Exception as e:
                print(f"Error fetching data: {e}")
            
            time.sleep(2)
        
        return df_day


    def crossover(self, df, param1, param2):
        sell = ((df[param1] < df[param2]) & (df[param1].shift(1) > df[param2].shift(1)))
        buy = ((df[param1] > df[param2]) & (df[param1].shift(1) < df[param2].shift(1)))
        sell = np.where(sell > 0, df["close"], "NaN")
        buy = np.where(buy > 0, df["close"], "NaN")
       
        return buy,sell
    
    def ema(self, data, window):
        ema = data.ewm(span=window).mean()
        return ema
    

    def save2csv(self, realfilename, df):
        # print(df)
        current_dir = str(Path(__file__).parent)
        filename = realfilename + ".csv"
        path_to_file = current_dir + "/csv/" + filename
        checkfile = Path(path_to_file)
        df.to_csv(path_to_file, mode="w", index=False, header=True)
        print("csv created")
        return "CSV Created"

    def getcsv(self, stock):
        current_dir = str(Path(__file__).parent)
        filename = stock + ".csv"
        path_to_file = current_dir + "/csv/" + filename
        df = pd.read_csv(path_to_file)
        return df

    def save2googlesheet(self, df, sheetname, sheet_identifier):
        if pygsheets is None:
            print("Error: pygsheets library not installed. Cannot save to Google Sheets.")
            return "Library not found"
            
        numberofrows = len(df.index)
        if numberofrows > 5000:  df = df.iloc[-5000:]
        
        # Look for gsheets.json in the same directory as this file or its scripts/ subfolder
        current_dir = Path(__file__).parent
        filename = current_dir / "gsheets.json"
        if not filename.exists():
            filename = current_dir / "scripts" / "gsheets.json"
        
        if not filename.exists():
            print(f"Error: Google Sheets credentials not found at {filename}")
            return "Credentials not found"

        gc = pygsheets.authorize(service_file=str(filename))
        sh = gc.open(sheetname)

        wks = None
        if isinstance(sheet_identifier, int):
            wks = sh[sheet_identifier]
        elif isinstance(sheet_identifier, str):
            try:
                wks = sh.worksheet_by_title(sheet_identifier)
            except pygsheets.WorksheetNotFound:
                wks = sh.add_worksheet(title=sheet_identifier, rows=5000, cols=len(df.columns))

        if wks:
            wks.clear()
            wks.set_dataframe(df, (1, 1))
        else:
            print(f"Error: Worksheet {sheet_identifier} not found and could not be created.")

    def backteststategy(self, stock, datadf):
        df = datadf[(datadf.signals == "Buy" ) | (datadf.signals == "Sell") | (datadf.signals == "Buyclose" ) | (datadf.signals == "Sellclose") ]
        df.reset_index(inplace=True)

     
        
        sf = pd.DataFrame(
                    columns=[
                        "stock",
                        "start_datetime",
                        "stop_datetime",
                        "duration",
                        "direction",
                        "buy",
                        "buyclose",
                        "sell",
                        "sellclose",
                        "profit_loss",
                        "percentage_profit",
                        "total_profit"
                    ]
                )


        winrate = 0
        total_profit = 0
        j = 1
        for i, row in df.iterrows():
            if i >= 1:
                prev = i-1 
                if df.loc[i, "signals"] =='Buyclose':
                
                    buyclose = df.loc[i, "close"]
                    buyclose = round(buyclose, 4)
                    stop_datetime = df.loc[i, "datetime"]
                    buy = df.loc[prev, "close"]
                    buy = round(buy, 4)
                    start_datetime = df.loc[prev, "datetime"]
                    profit_loss = float(buyclose) - float(buy)
                    if profit_loss > 0:
                        winrate = winrate + 1
                    total_profit = total_profit + profit_loss
                    total_profit = round(total_profit, 4)

                    start_datetime = df.loc[prev, "datetime"]
                    duration = str(stop_datetime - start_datetime)
                    percentage_profit = round(profit_loss / buy * 100, 2)
                
                    
                    sf.loc[j] = [
                                stock,
                                start_datetime,
                                stop_datetime,
                                duration,
                                'BUY',
                                buy,
                                buyclose,
                                0,
                                0,
                                profit_loss,
                                percentage_profit,
                                total_profit,
                            ]
                    j = j + 1
            

                elif df.loc[i, "signals"] =='Sellclose':

                    sellclose = df.loc[i, "close"]
                    sellclose = round(sellclose, 4)
                
                    stop_datetime = df.loc[i, "datetime"]
                    sell = df.loc[prev, "close"]
                    sell = round(sell, 4)
                    profit_loss = float(sell) - float(sellclose)
                    percentage_profit = round(profit_loss / sell * 100, 2)
                    if profit_loss > 0:
                        winrate = winrate + 1
                    total_profit = total_profit + profit_loss
                    total_profit = round(total_profit, 4)
                    start_datetime = df.loc[prev, "datetime"]
                    duration = str(stop_datetime - start_datetime)
    
                    sf.loc[j] = [
                        stock,
                        start_datetime,
                        stop_datetime,
                        duration,
                        'SELL',
                        sell,
                        sellclose,
                        0,
                        0,
                        profit_loss,
                        percentage_profit,
                        total_profit
                    ]
                    j = j + 1
        
        total_trades = sf.shape[0]
        sf["json"] = sf.to_json(orient="records", date_format="iso", date_unit="s", lines=True).splitlines()
        sf = sf.reset_index()

        print("Backtest Strategy")
        print(sf.shape)
        print(total_trades)
        print(winrate)
        return sf, total_trades,  winrate,total_profit


    def getgraphdata(self, df):
        df["json"] = df.to_json(orient="records", date_format="iso", date_unit="s", lines=True).splitlines()
        df = df.reset_index()

        graphapi = []

        for i, row in df.iterrows():
            
            jsondata = df.loc[i, "json"]
            json_object = json.loads(jsondata)
            graphapi.append(json_object)

        # print(type(Responsejson))
        return graphapi
    

    def dftojson(self, df):
        if df.empty:
            return []
        else:
            df["newjson"] = df.to_json(orient="records", date_format="iso", date_unit="s", lines=True).splitlines()
            df = df.reset_index(drop=True)
            json_data = []
            for i, row in df.iterrows():
                jsondata = df.loc[i, "newjson"]
                json_object = json.loads(jsondata)
                json_data.append(json_object)
            # print(type(Responsejson))
            return json_data


    def df2csv(self, df):
        try:
            df['start_datetime'] = pd.to_datetime(df['start_datetime'], unit='ms')
            df['end_datetime'] = pd.to_datetime(df['end_datetime'], unit='ms')
            print("----", df)
        except Exception as e:
            print("----", str(e))

        csv_string = df.to_csv("backtest.csv", index=False)
        return csv_string
    


    def buyandholdcalculation(self, df):
        print("step4")
        startprice = df["close"].iloc[0]
        endprice = df["close"].iloc[-1]
        startdate = df["datetime"].iloc[0]
        enddate = df["datetime"].iloc[-1]
        profitloss = endprice - startprice 
        duration = enddate - startdate 
        # print(profitloss)
        # print(duration)


    def checkdbbuysell(self, df):
        action= df["slope"].iloc[0]
        position=0
        symbol = df["symbol"].iloc[0]
         
        symbol =  symbol.split(":", 1)
        source = symbol[0]
        stock = symbol[1]
        ic(symbol)

        from simpleincome.models import StockSignal
        from simpleincome.serializers import StockSignalSerializer
    
        StockSignalInstance = StockSignal.objects.filter(stock=stock).filter(status=1)
        signalData = StockSignalSerializer(StockSignalInstance,many=True)

        signalsdatalength = len(signalData.data) 
        ic(signalsdatalength)
        for i, row in df.iterrows():
            if position == 0:
                if signalsdatalength==0:
                    if float(df.loc[i, "buy"]) > 0 :    
                            buy =  df.loc[i, "close"]
                            notes = df.loc[i, "signals"] = "Buy"
                            start_datetime = df.loc[i, "datetime"]
                            df.loc[i, "trigger"] = 1
                            position  = 0
                            # ic(i,start_datetime, notes)
                    elif float(df.loc[i, "sell"]) > 0  :     
                            sell =  df.loc[i, "close"]
                            notes = df.loc[i, "signals"] = "Sell"
                            start_datetime = df.loc[i, "datetime"]
                            df.loc[i, "trigger"] = 1
                            position  = 0
                            # ic(i,start_datetime, notes)
        df.reset_index(inplace=True)

        return df


    def checkbuysell(self, df):
        # action= df["slope"].iloc[0]
        
       
        # if df.loc[1, "action"] == "Positive":
        #     position = 1
        # else:
        #     position = 4
        position=0

        for i, row in df.iterrows():
            prev1, prev2, prev3 = i - 1, i - 2, i - 3
            
            if position == 0:
                try:
                    if float(df.loc[i, "buy"]) > 0 :    
                            buy =  df.loc[i, "close"]
                            notes = df.loc[i, "signals"] = "Buy"
                            start_datetime = df.loc[i, "datetime"]
                            df.loc[i, "trigger"] = 1
                            position  = 2
                            ic(i,start_datetime, notes)
                    elif float(df.loc[i, "sell"]) > 0  :     
                        sell =  df.loc[i, "close"]
                        notes = df.loc[i, "signals"] = "Sell"
                        start_datetime = df.loc[i, "datetime"]
                        df.loc[i, "trigger"] = 1
                        position  = 3
                        ic(i,start_datetime, notes)
                except:
                    buysell = 0

            # if position == 1:
            #     if float(df.loc[i, "buy"]) > 0 :    
            #             buy =  df.loc[i, "close"]
            #             notes = df.loc[i, "signals"] = "Buy"
            #             start_datetime = df.loc[i, "datetime"]
            #             df.loc[i, "trigger"] = 1
            #             position  = 2

            # elif position == 4:
            #     if float(df.loc[i, "sell"]) > 0 :     
            #             sell =  df.loc[i, "close"]
            #             notes = df.loc[i, "signals"] = "Sell"
            #             start_datetime = df.loc[i, "datetime"]
            #             df.loc[i, "trigger"] = 1
            #             position  = 3
            elif position == 2:
                if float(df.loc[i, "buyclose"]) > 0 :     
                        buyclose =  df.loc[i, "close"]
                        notes = df.loc[i, "signals"] = "Buyclose"
                        df.loc[i, "trigger"] = 1
                        profitloss = buyclose - buy
                        df.loc[i,"profitloss"] = profitloss = profitloss * float(df.loc[i, "qty"])
                        stop_datetime = df.loc[i, "datetime"]
                        df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
                        position  = 0
                        ic(i,stop_datetime, notes,profitloss)

                # if float(df.loc[i, "buyclose"]) >  float(df.loc[i, "uppertwo"] ) :     
                #         buyclose =  df.loc[i, "close"]
                #         notes = df.loc[i, "signals"] = "Buyclose"
                #         df.loc[i, "trigger"] = 1
                #         profitloss = df.loc[i,"profitloss"] = buyclose - buy
                #         stop_datetime = df.loc[i, "datetime"]
                #         df.loc[i, "duration" ]  = str(stop_datetime - start_datetime)
                #         position  = 0
                #         ic(stop_datetime, notes)


            elif position == 3:
                if float(df.loc[i, "sellclose"]) > 0 :     
                        sellclose =  df.loc[i, "close"]
                        notes = df.loc[i, "signals"] = "Sellclose"
                        df.loc[i, "trigger"] = 1
                        profitloss = sell - sellclose
                        profitloss = df.loc[i,"profitloss"] = profitloss * float(df.loc[i, "qty"])
                        stop_datetime = df.loc[i, "datetime"]
                        df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
                        position  = 0
                        ic(i,stop_datetime, notes,profitloss)


                # if float(df.loc[i, "sellclose"]) >  :     
                #         sellclose =  df.loc[i, "close"]
                #         notes = df.loc[i, "signals"] = "Sellclose"
                #         df.loc[i, "trigger"] = 1
                #         profitloss = df.loc[i,"profitloss"] = sell - sellclose
                #         stop_datetime = df.loc[i, "datetime"]
                #         df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
                #         position  = 0
                #         ic(stop_datetime, notes)

        df.reset_index(inplace=True)

        return df
    

    # def checkbuysell(df):
    #     action= df["slope"].iloc[0]
        
       
    #     # if df.loc[1, "action"] == "Positive":
    #     #     position = 1
    #     # else:
    #     #     position = 4
    #     position=0

    #     for i, row in df.iterrows():
    #         prev1, prev2, prev3 = i - 1, i - 2, i - 3
            
    #         if position == 0:
    #             try:
    #                 if float(df.loc[i, "buy"]) > 0 :    
    #                         buy =  df.loc[i, "close"]
    #                         notes = df.loc[i, "signals"] = "Buy"
    #                         start_datetime = df.loc[i, "datetime"]
    #                         df.loc[i, "trigger"] = 1
    #                         position  = 2
    #                         ic(i,start_datetime, notes)
    #                 elif float(df.loc[i, "sell"]) > 0  :     
    #                     sell =  df.loc[i, "close"]
    #                     notes = df.loc[i, "signals"] = "Sell"
    #                     start_datetime = df.loc[i, "datetime"]
    #                     df.loc[i, "trigger"] = 1
    #                     position  = 3
    #                     ic(i,start_datetime, notes)
    #             except:
    #                 buysell = 0

    #         # if position == 1:
    #         #     if float(df.loc[i, "buy"]) > 0 :    
    #         #             buy =  df.loc[i, "close"]
    #         #             notes = df.loc[i, "signals"] = "Buy"
    #         #             start_datetime = df.loc[i, "datetime"]
    #         #             df.loc[i, "trigger"] = 1
    #         #             position  = 2

    #         # elif position == 4:
    #         #     if float(df.loc[i, "sell"]) > 0 :     
    #         #             sell =  df.loc[i, "close"]
    #         #             notes = df.loc[i, "signals"] = "Sell"
    #         #             start_datetime = df.loc[i, "datetime"]
    #         #             df.loc[i, "trigger"] = 1
    #         #             position  = 3
    #         elif position == 2:
    #             if float(df.loc[i, "buyclose"]) > 0 :     
    #                     buyclose =  df.loc[i, "close"]
    #                     notes = df.loc[i, "signals"] = "Buyclose"
    #                     df.loc[i, "trigger"] = 1
    #                     profitloss = buyclose - buy
    #                     df.loc[i,"profitloss"] = profitloss = profitloss * float(df.loc[i, "qty"])
    #                     stop_datetime = df.loc[i, "datetime"]
    #                     df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
    #                     position  = 0
    #                     ic(i,stop_datetime, notes,profitloss)

    #             # if float(df.loc[i, "buyclose"]) >  float(df.loc[i, "uppertwo"] ) :     
    #             #         buyclose =  df.loc[i, "close"]
    #             #         notes = df.loc[i, "signals"] = "Buyclose"
    #             #         df.loc[i, "trigger"] = 1
    #             #         profitloss = df.loc[i,"profitloss"] = buyclose - buy
    #             #         stop_datetime = df.loc[i, "datetime"]
    #             #         df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
    #             #         position  = 0
    #             #         ic(stop_datetime, notes)


    #         elif position == 3:
    #             if float(df.loc[i, "sellclose"]) > 0 :     
    #                     sellclose =  df.loc[i, "close"]
    #                     notes = df.loc[i, "signals"] = "Sellclose"
    #                     df.loc[i, "trigger"] = 1
    #                     profitloss = sell - sellclose
    #                     profitloss = df.loc[i,"profitloss"] = profitloss * float(df.loc[i, "qty"])
    #                     stop_datetime = df.loc[i, "datetime"]
    #                     df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
    #                     position  = 0
    #                     ic(i,stop_datetime, notes,profitloss)


    #             # if float(df.loc[i, "sellclose"]) >  :     
    #             #         sellclose =  df.loc[i, "close"]
    #             #         notes = df.loc[i, "signals"] = "Sellclose"
    #             #         df.loc[i, "trigger"] = 1
    #             #         profitloss = df.loc[i,"profitloss"] = sell - sellclose
    #             #         stop_datetime = df.loc[i, "datetime"]
    #             #         df.loc[i, "duration"]  = str(stop_datetime - start_datetime)
    #             #         position  = 0
    #             #         ic(stop_datetime, notes)

    #     df.reset_index(inplace=True)

    #     return df
    

    def buysell(self, df):
        action= df["slope"].iloc[0]
        
       
        # if df.loc[1, "action" ] == "Positive":
        #     position = 1
        # else:
        #     position = 4
        position=0

        for i, row in df.iterrows():
            try:
                if float(df.loc[i, "buy"]) > 0 :    
                        buy =  df.loc[i, "close"]
                        notes = df.loc[i, "signals"] = "Buy"
                        start_datetime = df.loc[i, "datetime"]
                        df.loc[i, "trigger"] = 1
                        position  = 2
                        ic(i,start_datetime, notes)
                elif float(df.loc[i, "sell"]) > 0  :     
                    sell =  df.loc[i, "close"]
                    notes = df.loc[i, "signals"] = "Sell"
                    start_datetime = df.loc[i, "datetime"]
                    df.loc[i, "trigger"] = 1
                    position  = 3
                    ic(i,start_datetime, notes)
            except:
                buysell = 0


        

        return df
    

    def triggeralerts(self, df):
        signals = df["signals"].iloc[-2]
        if signals == "Buy" or  signals == "Buyclose" or signals =="Sell" or signals == "Sellclose" :
            print("triggeralert")
            # Alerts.trigger(df) # Alerts not defined in this scope
        return "sucess"
    

    def transactions(self, datadf):
        # df = datadf[(datadf.signals == "Buy" ) | (datadf.signals == "Sell") | (datadf.signals == "Buyclose" ) | (datadf.signals == "Sellclose") ]
        
        datadf['signals'] = datadf['signals'].str.strip().str.capitalize()

        # Filter using the corrected values
        df = datadf[datadf['signals'].isin(["Buy", "Sell", "Buyclose", "Sellclose"])]

       
        # df = df.reset_index(inplace=True)
        # self.save2googlesheet(df, "standard-deviation", 10)
        print(df)
        return df
          

    def showprofitloss(self, stock):
        df = self.getcsv(stock)
        response = df.to_json(orient="records", date_format="iso", date_unit="s")
        return response
    
    def benchmarkusroi(self, startdate, enddate):
       
        startdate = datetime.strptime(startdate, '%Y-%m-%d')
        enddate = datetime.strptime(enddate, '%Y-%m-%d')
        duration =  enddate - startdate
        duration = int(duration.days)
        ic(duration)
        data = {'stock': 'US30', 'source': 'CAPITALCOM', 'interval': '1D'}
        df = self.getdata(data['stock'], data['source'], data['interval'], duration)
        df = df.reset_index()
        startprice = df["close"].iloc[0]
        endprice  = df["close"].iloc[-1]
        totalprofit = endprice - startprice
        benchmarkroi = totalprofit/startprice  * 100

        ic(startdate)
        ic(enddate)
        ic(duration)
        ic(startprice)
        ic(endprice)
        ic(totalprofit)
        ic(benchmarkroi)
        benchmarkindex = data['stock']
        return benchmarkindex, benchmarkroi

    def stats(df,tf,total_trades,winrate,total_profit):
        stock = df["symbol"].iloc[0]
        investment = df["close"].iloc[0] 
        startdate = df["datetime"].iloc[0]
        enddate  = df["datetime"].iloc[-1]
        duration =  enddate - startdate
        roi = total_profit
        
        yearmultiplier = 365/duration.days 

        yearlyprofit = roi * yearmultiplier
        yearlyroi = yearlyprofit/investment * 100

        # benchmarkstock,benchmarkroi = Quant.benchmarkusroi(startdate,enddate)
        
        try:
            winpercentage = winrate/total_trades * 100
        except ZeroDivisionError:
            winpercentage = 0

        stats = {}
        stats['stock'] = stock 
        stats['startdate'] = startdate 
        stats['enddate'] = enddate 
        stats['duration'] = str(duration)
        stats['investment'] = df["close"].iloc[0] 
        stats['roi'] = roi
        stats['yearmultiplier'] = yearmultiplier
        stats['yearlyprofit'] = round(yearlyprofit,3)
        stats['yearlyroi'] = round(yearlyroi,2)
        stats['total_trades'] = round(total_trades,2)
        stats['winrate'] = round(winrate,2)
        stats['winpercentage'] = round(winpercentage,2)
        # stats['benchmarkstock'] = benchmarkstock
        # stats['benchmarkroi'] = round(benchmarkroi,2)

        ic(stats)
        return stats
    

    @staticmethod
    def std_channel(data, period, factor):
        """
        Calculate the upper and lower bands of the standard deviation channel.
        Args:
            data (ndarray): A numpy array of prices.
            period (int): The period for which to calculate the standard deviation.
            factor (float): The factor by which to multiply the standard deviation to get the band.
        Returns:
            (ndarray, ndarray): A tuple of two numpy arrays representing the upper and lower bands of the standard deviation channel.
        """
        std = np.std(data[-period:])
        upper_band = np.mean(data[-period:]) + factor * std
        lower_band = np.mean(data[-period:]) - factor * std
        return upper_band, lower_band
    

    def supertrendc2(self, df, atr_period=18, multiplier=3):

        atr_period = float(atr_period)
        multiplier = float(multiplier)
        # issue with forex --

       
        high = df["high"]
        low = df["low"]
        close = df["close"]


        # calculate ATR
        price_diffs = [high - low, high - close.shift(), close.shift() - low]
        tr = pd.concat(price_diffs, axis=1)
        tr = tr.abs().max(axis=1)

        df["tr"] = tr
        df["atr"] = atr = df["tr"].ewm(alpha=1 / atr_period, min_periods=atr_period).mean()

        # df["ema1"] = tradeindicators.ema(df["close"], 100)
        # df["ema2"] = tradeindicators.ema(df["close"], 200)

        # HL2 is simply the average of high and low prices
        df["hl2"] = hl2 = (high + low) / 2
        final_upperband = upperband = hl2 + (multiplier * atr)
        final_lowerband = lowerband = hl2 - (multiplier * atr)
        supertrend = [True] * len(df)
        trade = [True] * len(df)

        for i in range(1, len(df.index)):
            curr, prev = i, i - 1

            # if current close price crosses above upperband
            if close[curr] > final_upperband[prev]:
                supertrend[curr] = 1
            # if current close price crosses below lowerband
            elif close[curr] < final_lowerband[prev]:
                supertrend[curr] = 0
            # else, the trend continues
            else:
                supertrend[curr] = supertrend[prev]
                # adjustment to the final bands
                if supertrend[curr] == 1 and final_lowerband[curr] < final_lowerband[prev]:
                    final_lowerband[curr] = final_lowerband[prev]
                if supertrend[curr] == 0 and final_upperband[curr] > final_upperband[prev]:
                    final_upperband[curr] = final_upperband[prev]

                # remove bands depending on the trend direction for visualization
                if supertrend[curr] == 1:
                    final_upperband[curr] = np.nan
                else:
                    final_lowerband[curr] = np.nan

        df["supertrend"] = supertrend
        df["supertrend1"] = df["supertrend"].shift(periods=1)

        df["finalc2_lowerband"] = final_lowerband
        df["finalc2_upperband"] = final_upperband

        # df = pd.DataFrame(df)
        # df.reset_index(inplace=True)

        return df
    

    def mastrategy(df):
        df['ma'] = ta.SMA(df['close'],timeperiod=21)
        df['ema'] = ta.EMA(df['close'], timeperiod = 5)
        buy,sell = Quant.crossover(df,"close","ema")
        df["sellclose"] = buy
        df["buyclose"] = sell
        df["sell"] = df["buyclose"].shift(1)
        df["buy"] = df["sellclose"].shift(1)

        return df
    

    def backtest_mastrategy(data):
        print(data)
        df = Quant.getdata(data['stock'], data['sourceexch'],data['interval'],data['length'])
        df = Quant.mastrategy(df)
        df = Quant.checkbuysell(df)
        Quant.graph(df)
        sf,total_trades, winrate,total_profit = Quant.backteststategy(data['stock'],df)
        stockbuysell = data['stock'] + "-buy-sell"
        # Quant.save2csv(data['stock'],df)
        # Quant.save2csv(stockbuysell,sf)
        # Quant.save2googlesheet(df, data['googlesheetname'], 0)
        # Quant.save2googlesheet(sf, data['googlesheetname'], 1)
        print(data)


    def backtest_supertrend(data):
        print(data)
        df = Quant.getdata(data['stock'], data['sourceexch'],data['interval'],data['length'])
        # df = Quant.mastrategy(df)
        df = Quant.supertrendc2(df)
        Quant.save2googlesheet(df, data['googlesheetname'], 0)

        df["buy"] =(df["supertrend"] == 0 ) & (df["supertrend1"] == 1)
        df["sell"] =(df["supertrend"] == 1)  & ( df["supertrend"] == 1)

        for i, row in df.iterrows():
            if df.loc[i, "supertrend"] == 1 and df.loc[i, "supertrend1"] == 0 :     
                df.loc[i, "sellclose"] = df.loc[i, "close"]
            elif df.loc[i, "supertrend"] == 0 and df.loc[i, "supertrend1"] == 1 :     
                df.loc[i, "buyclose"] = df.loc[i, "close"]

        df["sell"] = df["buyclose"].shift(1)
        df["buy"] = df["sellclose"].shift(1)
        df = Quant.checkbuysell(df)
        Quant.graph(df)
        sf,total_trades, winrate,total_profit = Quant.backteststategy(data['stock'],df)
        stockbuysell = data['stock'] + "-buy-sell"
        Quant.save2csv(data['stock'],df)
        Quant.save2csv(stockbuysell,sf)
        Quant.save2googlesheet(df, data['googlesheetname'], 0)
        Quant.save2googlesheet(sf, data['googlesheetname'], 1)
        print("CSV")
        print(data)
    
    
    def getstrikeprice(fdatetime,strikeprice):
        df = Quant.getdata(strikeprice, "NSE", "3", "2000")
        datetime_filter = pd.to_datetime(fdatetime)
        
        # Convert datetime to pandas datetime format
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # Filter DataFrame for datetime within ±10 minutes
        time_window = pd.Timedelta(minutes=10)
        filtered_df = df[
            (df['datetime'] >= datetime_filter - time_window) & 
            (df['datetime'] <= datetime_filter + time_window)
        ]
        # Get the latest row from filtered DataFrame
        latest_data = filtered_df.iloc[-1] if not filtered_df.empty else None

        # Get the close price from the latest data
        if latest_data is not None:
            close_price = latest_data['close']
            print(f"Latest close price: {close_price}")
            return close_price
        else:
            print("No close price available")
            close_price = None
            return close_price
    



    def graph(df):
            # numberofrows = len(df.index)
            # if numberofrows > 600:
            #     df = df[-200:]
            fig = go.Figure()

            # df['datetime'] = df['datetime'] + timedelta(hours=8)
            # declare figure
            # Create subplots and mention plot grid size

            fig = make_subplots(
                rows=1,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.1,
                subplot_titles=("OHLC", "Volume"),
            )



            # fig.add_trace(go.Scatter(x=df['index'], y=df['supertrend'], line_shape='spline', line_smoothing=1.3,
            #                         line=dict(color='blue', width=.7), name='close'), row=1, col=1)
            try:   
                fig.add_trace(go.Scatter(x=df['index'], y=df['finalc2_lowerband'], line_shape='spline', line_smoothing=1.3,
                                    line=dict(color='green', width=.7), name='close'), row=1, col=1)
            except:
                print("no attributes as finalc2_upperband")


            try:
                fig.add_trace(go.Scatter(x=df['index'], y=df['finalc2_upperband'], line_shape='spline', line_smoothing=1.3,
                                line=dict(color='red', width=.7), name='close'), row=1, col=1)
            except:
                print("no attributes as finalc2_upperband")

            try:
                fig.add_trace(go.Scatter(x=df['index'], y=df['close'], line_shape='spline', line_smoothing=1.3,
                                    line=dict(color='blue', width=.7), name='close'), row=1, col=1)
            except:
                print("no attributes as finalc2_upperband")

            # try:
            #     fig.add_trace(go.Scatter(x=df['index'], y=df['ma'], line_shape='spline', line_smoothing=1.3,
            #                         line=dict(color='orange', width=.7), name='ma'), row=1, col=1)
            # except:
            #     print("no attributes as finalc2_upperband")



            # try:
            #     fig.add_trace(go.Scatter(x=df['index'], y=df['ema'], line_shape='spline', line_smoothing=1.3,
            #                                 line=dict(color='purple', width=.7), name='ema'), row=1, col=1)
            # except:
            #     print("no attribute")
            
            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["buy"],
                        mode="markers",
                        name="buy",
                        line=dict(width=1, color="green"),
                    ),row=1, col=1
                )
            except:
                print("no attributes as buy")

            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["buyclose"],
                        mode="markers",
                        name="buyclose",
                        line=dict(width=1, color="darkblue"),
                        
                    ),row=1, col=1
                )
            except:
                print("no attributes as buy")

            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["sell"],
                        mode="markers",
                        name="sell",
                        line=dict(width=1, color="red"),
                    ),row=1, col=1
                )
            except:
                print("no attributes as sell")


            try:
                fig.add_trace(
                    go.Scatter(
                        x=df["index"],
                        y=df["sellclose"],
                        mode="markers",
                        name="sellclose",
                        line=dict(width=1, color="orange"),
                    ),row=1, col=1
                )
            except:
                print("no attributes as sellclose")


            fig.update_layout(title="Stock Analysis", yaxis_title="OHLC", height=900, width=1500)
            fig.update(layout_xaxis_rangeslider_visible=False)
            fig.show()


    def cal_sharpe_ratio(df, initial_investment = 20000):
        df['profitloss'].fillna(0, inplace=True)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)


        daily_profitloss = df['profitloss'].resample('D').sum()

        daily_returns = daily_profitloss / initial_investment
        avg_return = daily_returns.mean()
        std_dev = daily_returns.std()

        # Assume a risk-free rate (annual) and convert to daily
        risk_free_rate = 0.05 / 252  # 252 trading days in a year

        # Calculate Sharpe Ratio
        sharpe_ratio = (avg_return - risk_free_rate) / std_dev

        return sharpe_ratio