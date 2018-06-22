from flask import Flask, render_template, request, jsonify
from sps_engineering_Lib_dataQuery import databasemanager
from sps_engineering_Lib_dataQuery import confighandler
from sps_engineering_Lib_dataQuery import dates
import json
import plotly
import datetime
import pandas as pd
import numpy as np
from pprint import pprint

# initialiasation de Flask
app = Flask(__name__)

# charge la configuration
conf = confighandler.loadConf()
# charge la configuration des alarmes
conf_alarm = confighandler.loadAlarm()
# time out
conf_timeout = confighandler.readTimeout()
# Read mode alarm
conf_readmode = confighandler.readMode()
# connection a la base de donnée
try:
    db = databasemanager.DatabaseManager('localhost', 5432)
    db.init()
except:
    raise Exception('connection to the database impossible')

# si l'entête renvoye une erreur 404
@app.errorhandler(404)
def error404(error):
    return render_template('page_not_found.html'), 404


# page principal (index)
@app.route("/")
def index():
    results = getAllLast()
    return render_template('index.html', results=results)


# page pour voir le graphique du la valeur demandé
@app.route("/view/<string:table>/<string:devices>", methods=['GET', 'POST'])
def view(table, devices):
    error = []
    date_aff = []
    date_end = ""

    for item in conf:
        if item.tablename == table:
            index = item.keys.index(devices)
            ylabel = item.ylabels[index]

    info = dict(
        table=table,
        key=devices,
        ylabel=ylabel,
    )

    if request.method == 'POST':
        date_start = datetime.datetime(int(request.form['year_start']), int(request.form['month_start']), int(request.form['day_start'])).date()
        date_end = datetime.datetime(int(request.form['year_end']), int(request.form['month_end']), int(request.form['day_end'])).date()
    else:
        last_day = db.last(table=table, cols=devices)
        last_day = dates.num2date(last_day['tai']).date()
        date_start = last_day
    if date_end:
        if date_start > date_end:
            error.append("date end is upper date start")
        if date_end > datetime.datetime.now().date():
            error.append("date end not yet passed")
    if date_start > datetime.datetime.now().date():
        error.append("date start not yet passed")

    try:
        query = db.dataBetween(table=table, cols=devices, start=str(date_start), end=str(date_end + datetime.timedelta(days=1)) if date_end else '')
    except:
        error.append("error query")
        last_day = db.last(table=table, cols=devices)
        last_day = dates.num2date(last_day['tai']).date()
        date = last_day
        query = db.dataBetween(table=table, cols=devices, start=str(date))
    finally:
        for donne in query['tai']:
            date_aff.append(dates.num2date(donne).isoformat().replace('T', ' ')[:-13])

        del query['id']
        del query['tai']
        data = query[devices]

        # donnée pour le graph
        graphs = [
            dict(
                data=[
                    dict(
                        x=date_aff,
                        y=data
                    )
                ]
            )
        ]

        graphjson = json.dumps(graphs, cls=plotly.utils.PlotlyJSONEncoder)

        legend_x = [str(date_start), str(date_end) if date_end != "" else str(datetime.datetime.now() - datetime.timedelta(hours=2))]

        return render_template('view.html', error=error, graphjson=graphjson, legend_x=legend_x, info=info, date=datetime.datetime.now().date())


# page de qui actualise les dernier donné
@app.route("/refresh_all")
def refresh_all():
    results = getAllLast()
    text = ""

    for item in results[0]:
        if filter_readmodes(item) is True:
            text += "<div class=\"" + item + "\">"
        else:
            text += "<div class=\"" + item + " offline\">"
        text += "<h3>" + item + "</h3>"
        for device in results[0][item]:
            text += "<ul>"
            if filter_timeouts(device['table_name']) is True:
                text += "<li class=\"Timeout\">" + device['label_device'] + " (" + device['date'] + ") " + filter_dates(device['date']) + "</li>"
            else:
                text += "<li>" + device['label_device'] + " (" + device['date'] + ") " + filter_dates(device['date']) + "</li>"
            text += "<ul>"
            for idx, keys in enumerate(device['label_keys']):
                key = keys
                data = device['datas'][idx]
                if filter_alarms(device['table_name'], key, data)[0] is True:
                    if filter_alarms(device['table_name'], key, data)[1] is True:
                        text += "<li class =\"Alert_launch\"><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + key + "</a > : " + str(np.float64(data).item()) + " " + device['units'][idx] + " </li>"
                    else:
                        text += "<li class =\"Alert_act\"><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + key + "</a > : " + str(np.float64(data).item()) + " " + device['units'][idx] + "</li>"
                else:
                    if filter_ranges(data, device['range']) is True:
                        text += "<li class =\"error\"><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + key + "</a > : " + str(np.float64(data).item()) + " " + device['units'][idx] + " &#9888; </li>"
                    else:
                        text += "<li><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + key + "</a > : " + str(np.float64(data).item()) + " " + device['units'][idx] + " </li>"
            text += "</ul>"
            text += "</ul>"
        text += "</div>"

    return text


# page qui actualise le graph (AJAX)
@app.route("/refreshGraph")
def res():
    a = request.args.get('a')
    b = request.args.get('b')

    req = db.last(table=a, cols=b)

    date = dates.num2date(req.tai).isoformat().replace('T', ' ')[:-13]
    del req['id']
    del req['tai']

    donne = req[b]

    return jsonify(result=donne, date=date)


# recupere toutes les dernieres données
def getAllLast():
    result_blue = []
    result_red = []
    result_ait = []

    for item in conf:
        result = db.last(table=item.tablename, cols=','.join(item.keys))
        date_format = dates.num2date(result['tai']).isoformat().replace('T', ' ')[:-13]
        del result['id']
        del result['tai']

        donne = []
        for key in item.keys:
            donne.append(result[key])

        if item.tablename[4] == 'b':
            result_blue.append(dict(
                table_name=item.tablename,
                label_device=item.deviceLabel,
                date=date_format,
                key=item.keys,
                label_keys=item.labels,
                range=item.ranges,
                datas=donne,
                units=item.units
            ))
        elif item.tablename[4] == 'r':
            result_red.append(dict(
                table_name=item.tablename,
                label_device=item.deviceLabel,
                date=date_format,
                key=item.keys,
                label_keys=item.labels,
                range=item.ranges,
                datas=donne,
                units=item.units
            ))
        else:
            result_ait.append(dict(
                table_name=item.tablename,
                label_device=item.deviceLabel,
                date=date_format,
                key=item.keys,
                label_keys=item.labels,
                range=item.ranges,
                datas=donne,
                units=item.units
            ))

    results = [
        dict(
            xcu_r1=result_red,
            xcu_b1=result_blue,
            aitroom=result_ait
        )
    ]
    return results


# filtre
# lit le readmode dans le fichier de configuration et retourne false si le device n'est pas en operation
def filter_readmodes(name):
    operation = True

    if conf_readmode[name] != 'operation':
        operation = False

    return operation


# lit les time out dans le fichier de configuration de retourne true si le device a un time out
def filter_timeouts(table):
    stop = False

    for item in conf_timeout:
        if item == table:
            stop = True

    return stop


# compare la date de la dernier valeur à c'elle de maintenant pour voir si la valeur est a jour
def filter_dates(date):
    dates = date[:-9].split('-')
    date = datetime.datetime(int(dates[0]), int(dates[1]), int(dates[2])).date()
    if date < datetime.datetime.now().date():
        return "Value not update"
    else:
        return ""


# lit les limites du device dans le fichier de configuration et retourne true si le donne est pas entre c'est valeur
def filter_ranges(data, range):
    range = range[0].split(';')
    if data < float(range[0]) or data > float(range[1]):
        return True
    else:
        return False


# lit le fichier de configuaration et retourne find à true il a une alarme et error à true si l'alarme est activé
def filter_alarms(table, key, data):
    find = False
    error = False
    i = 0
    while find is False and i < len(conf_alarm):
        if conf_alarm[i].tablename == table and conf_alarm[i].key == key:
            find = True
            if float(conf_alarm[i].ubound) < data or float(conf_alarm[i].lbound) > data:
                error = True
        i = i + 1

    return find, error


# filtre utiliser dans le code html
@app.context_processor
def utility_processor():
    def filter_alarm(table, key, data):
        return filter_alarms(table, key, data)

    def filter_range(data, range):
        return filter_ranges(data, range)

    def filter_timeout(table):
        return filter_timeouts(table)

    def filter_readmode(name):
        return filter_readmodes(name)

    def filter_date(date):
        return filter_dates(date)

    return dict(filter_alarm=filter_alarm, filter_range=filter_range, filter_timeout=filter_timeout, filter_readmode=filter_readmode, filter_date=filter_date)


@app.route('/test')
def test():
    return render_template('test.html')


# lance l'application
if __name__ == '__main__':
    app.run(threaded=True)