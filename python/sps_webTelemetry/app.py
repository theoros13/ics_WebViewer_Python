from flask import Flask, render_template, request, jsonify
from sps_engineering_Lib_dataQuery import databasemanager
from sps_engineering_Lib_dataQuery import confighandler
from sps_engineering_Lib_dataQuery import dates
import json
import plotly
import datetime
import pandas as pd
import numpy as np
import re
from pprint import pprint

# initialiasation de Flask
app = Flask(__name__)

# charge la configuration
conf = confighandler.loadConf()
# time out
conf_timeout = confighandler.readTimeout()
# Read mode alarm
# conf_readmode = confighandler.readMode()
# connection a la base de donnée
try:
    # connection base pour les alarmes pour la page main
    db_alarm = databasemanager.DatabaseManager('localhost', 5432, 'alarmhandler')
    # connection pour les donées
    db = databasemanager.DatabaseManager('localhost', 5432)
    # initialisation
    db.init()
    db_alarm.init()
    conf_readmode = db_alarm.loadMode()
except:
    raise Exception('connection to the database impossible')


@app.errorhandler(404)
def error404(error):
    """
        function if the url is not defined
        :param error:
        :return: templates > page_not_found.htlm
        """
    return render_template('page_not_found.html'), 404


@app.route("/")
def index():
    """
    show the most importante information
    :return: templates > index.html, camera, enu, ait
    """
    alarm = db_alarm.loadAlarms()
    camera = []
    enu = []
    ait = []

    for name in alarm:
        datas = []
        datess = []
        tablenames = []
        keys = []
        labels = []
        limits = []

        mode = alarm[name].mode

        for device in alarm[name].alarms:
            if mode != 'offline':

                data = db.last(table=device.tablename.lower(), cols=device.key)
                date = dates.num2date(data['tai']).isoformat().replace('T', ' ')[:-13]
                del data['id']
                del data['tai']

                if type(device.ubound) == str:
                    device.ubound = device.ubound.replace('-', '')
                if type(device.lbound) == str:
                    device.lbound = device.lbound.replace('-', '')

                datas.append(data[device.key])
                datess.append(date)
                tablenames.append(device.tablename)
                keys.append(device.key)
                labels.append(device.label)
                limits.append([float(device.lbound), float(device.ubound)])

        if re.match("\d", name[1]):
            camera.append(
                dict(
                    mode=mode,
                    name=name,
                    table=tablenames,
                    key=keys,
                    label=labels,
                    limit=limits,
                    data=datas,
                    date=datess
                )
            )

        elif name[0] == 'e':
            enu.append(
                dict(
                    mode=mode,
                    name=name,
                    table=tablenames,
                    key=keys,
                    label=labels,
                    limit=limits,
                    data=datas,
                    date=datess
                )
            )
        else:
            ait.append(
                dict(
                    mode=mode,
                    name=name,
                    table=tablenames,
                    key=keys,
                    label=labels,
                    limit=limits,
                    data=datas,
                    date=datess
                )
            )
    return render_template('index.html', cameras=camera, enus=enu, aits=ait)


@app.route("/see_all")
def see_all():
    """
    principal page
    show all devices and the information of this
    :return: templates > see_all.html, results
    """
    results = getAllLast()
    return render_template('see_all.html', results=results)


@app.route("/view/<string:table>/<string:devices>", methods=['GET', 'POST'])
def view(table, devices):
    """
    show the plot of the devices selected
    :param table:
    :param devices:
    :return: templates > view.html, error, graphjson, legend_x, info, date of today
    """
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

        # data to the graph
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


@app.route("/refresh_all")
def refresh_all():
    """
    refresh the page see_all
    :return: text (html code)
    """
    results = getAllLast()
    text = ""

    for item in results[0]:
        text += "<div class=\"" + item + " " + filter_readmodes(item) + "\">"
        text += "<h3>" + item + "</h3>"
        for device in results[0][item]:
            text += "<ul>"
            text += "<li><span  class=\"" + filter_timeouts(device['table_name']) +"\" >" + device['label_device'] + " (" + device['date'] + ") " + filter_dates(device['date']) + "</span></li>"
            text += "<ul>"
            for idx, keys in enumerate(device['label_keys']):
                key = device['key'][idx]
                data = device['datas'][idx]
                alarm = filter_alarms(device['table_name'], key, data)
                if alarm[0] is True:
                    if alarm[1] is True:
                        text += "<li><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + keys + "</a > : <span class =\"Alert_launch\">" + str(np.float64(data).item()) + " " + device['units'][idx] + " </span> </li>"
                    else:
                        text += "<li><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + keys + "</a > : <span class=\"Alert_act\">" + str(np.float64(data).item()) + " " + device['units'][idx] + "</span> </li>"
                else:
                    if filter_ranges(data, device['range']) is True:
                        text += "<li><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + keys + "</a > : <span class=\"error\">" + str(np.float64(data).item()) + " " + device['units'][idx] + " &#9888; </span> </li>"
                    else:
                        text += "<li><a href=\"view/" + device['table_name'] + "/" + device['key'][idx] + " \">" + keys + "</a > : " + str(np.float64(data).item()) + " " + device['units'][idx] + " </li>"
            text += "</ul>"
            text += "</ul>"
        text += "</div>"

    return text


@app.route("/refreshGraph")
def res():
    """
    get the last value of the devices show in the plot
    :return: donne, date
    """
    a = request.args.get('a')
    b = request.args.get('b')

    req = db.last(table=a, cols=b)

    date = dates.num2date(req.tai).isoformat().replace('T', ' ')[:-13]
    del req['id']
    del req['tai']

    donne = req[b]

    return jsonify(result=donne, date=date)


def getAllLast():
    """
    get the last value of all devices
    :return: results
    """
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
def filter_readmodes(actor_name):
    """
    get the mode of the actor
    :param actor_name:
    :return: the mode of the actor
    """
    conf_readmode =db_alarm.loadMode()
    res = {}
    name2actors = {'b1': ['ccd_b1', 'xcu_b1'],
                   'r1': ['ccd_r1', 'xcu_r1'],
                    'cleanroom':['aitroom'],
                    'watercooling':['aitroom']}

    for name, mode in conf_readmode.items():
        try:
            actors = name2actors[name]
            for actor in actors:
                res[actor] = mode
        except KeyError:
            pass
    return res[actor_name]


def filter_timeouts(table):
    """
    see if the table has a timeout
    :param table:
    :return: 'timeout' if the table has a timeout or nothing
    """
    for item in conf_timeout:
        if item == table:
            return 'timeout'

    return ''


def filter_dates(date):
    """
    see if the date send is today
    :param date:
    :return: if the date is not same today return "Value not update" else nothing
    """
    dates = date[:-9].split('-')
    date = datetime.datetime(int(dates[0]), int(dates[1]), int(dates[2])).date()
    if date < datetime.datetime.now().date():
        return "Value not update"
    else:
        return ""


def filter_ranges(data, range):
    """
    check if the data is in good range
    :param data:
    :param range:
    :return: true if is not good and false if is good
    """
    range = range[0].split(';')
    if data < float(range[0]) or data > float(range[1]):
        return True
    else:
        return False


def filter_alarms(table, key, data):
    """
    see if the devices has an alarm
    :param table:
    :param key:
    :param data:
    :return: find : true if he has an alarm or false if he has not an alarm
            error : true if the alarm is launch
    """
    conf_alarm = db_alarm.loadAlarms()
    find = False
    error = False
    for name in conf_alarm:
        for device in conf_alarm[name].alarms:
            if table == device.tablename.lower() and key == device.key:
                find = True
                if type(device.ubound) == str:
                    device.ubound = device.ubound.replace('-', '')
                if type(device.lbound) == str:
                    device.lbound = device.lbound.replace('-', '')

                if data < float(device.lbound) or data >= float(device.ubound):
                    error = True

    return find, error


@app.context_processor
def utility_processor():
    """
    filter utils in the hmtl code
    :return: filter_alarm, filter_range, filter_timeout, filter_readmode, filter_date
    """
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


# launch the server
if __name__ == '__main__':
    app.run(threaded=True)