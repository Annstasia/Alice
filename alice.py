from flask import Flask, request
import logging
import json
import pymorphy2
import requests

app = Flask(__name__)
sessionStorage = {}

logging.basicConfig(level=logging.INFO, filename='app.log', format='%(asctime)s %(levelname)s %(name)s %(message)s')


@app.route('/post', methods=['POST'])
def main():
    logging.info('Request: %r', request.json)

    response = {
        'session': request.json['session'],
        'version': request.json['version'],
        'response': {
            'end_session': False
        }
    }

    handle_dialog(response, request.json)

    logging.info('Request: %r', response)

    return json.dumps(response)


def handle_dialog(res, req):
    user_id = req['session']['user_id']
    if req['session']['new']:
        res['response']['text'] = 'Привет! Я могу найти улицу вашего имени. Введите имя!'
        sessionStorage[user_id] = {}
        # Здесь будут храниться координаты найденных объектов
        sessionStorage[user_id]['coords'] = []
        res['response']['buttons'] = [
            {
                'title': 'помощь',
                'hide': True
            }
        ]
        return
    else:
        # Проверка вызова помощи
        if 'помощь' in req['request']['nlu']['tokens']:
            res['response']['text'] = 'Для поиска улицы введите имя или фамилию. Если улица будет' \
                                      ' обнаружена, у Вас будет возможность посмотреть ее на карте.' \
                                      ' Если улица не будет обнаружена, но найдется подходщий ' \
                                      'географический объект - будет выведен он.'
            # Если в sessionStorage[user_id]['coords'] указаны координаты,
            # то можно просмотреть изображения объекта
            # При вызове помощи не предпологается повторный вызов, поэтому данной кнопки нет
            if sessionStorage[user_id]['coords']:
                res['response']['buttons'] = [
                    {
                        "title": "Посмотреть гибридную карту",
                        "url": "http://static-maps.yandex.ru/1.x/?ll=" + \
                               ','.join(sessionStorage[user_id]['coords']) + "&l=sat,skl&spn=0.0016457,0.000619",
                        "hide": True
                    },
                    {
                        "title": "Посмотреть схематичную карту",
                        "url": "http://static-maps.yandex.ru/1.x/?ll=" + \
                               ','.join(sessionStorage[user_id]['coords']) + "&l=map&spn=0.0016457,0.000619",
                        "hide": True
                    },
                    {
                        "title": "Посмотреть спутниковую карту",
                        "url": "http://static-maps.yandex.ru/1.x/?ll=" + \
                               ','.join(sessionStorage[user_id]['coords']) + "&l=sat&spn=0.0016457,0.000619",
                        "hide": True
                    }
                ]
            return
        if 'посмотреть' in req['request']['nlu']['tokens']:
            # Объеденяет вызов всех кнопок просмотра изображения
            res['response']['text'] = 'Введите новое имя или посмотрите изображения улицы'
            res['response']['buttons'] = [
                {
                    "title": "Посмотреть гибридную карту",
                    "url": "http://static-maps.yandex.ru/1.x/?ll=" + \
                           ','.join(sessionStorage[user_id]['coords']) + "&l=sat,skl&spn=0.0016457,0.000619",
                    "hide": True
                },
                {
                    "title": "Посмотреть схематичную карту",
                    "url": "http://static-maps.yandex.ru/1.x/?ll=" + \
                           ','.join(sessionStorage[user_id]['coords']) + "&l=map&spn=0.0016457,0.000619",
                    "hide": True
                },
                {
                    "title": "Посмотреть спутниковую карту",
                    "url": "http://static-maps.yandex.ru/1.x/?ll=" + \
                           ','.join(sessionStorage[user_id]['coords']) + "&l=sat&spn=0.0016457,0.000619",
                    "hide": True
                },
                {
                    'title': 'помощь',
                    'hide': True
                }
            ]
            return

        # Поиск имени во входной строке
        name = get_name(req)
        # Обнуляется координаты. Все действия, связанные с предыдущими координатами отлавливаются раньше
        # Если программа дошла до данной строки, то запрос связан с новым именем
        sessionStorage[user_id]['coords'] = []
        # Если Алиса не обнаружила имя
        if not name:
            res['response']['text'] = 'Не расслышала имя. Повтори, пожалуйста!'
            res['response']['buttons'] = [
                {
                    'title': 'помощь',
                    'hide': True
                }
            ]
            return
        if name[0] or name[1]:
            # Если введено имя с фамилией
            if name[0] and name[1]:
                # При вводе женской фамилии предпочтиетльно найти улицу, носящую женскую фамилию.
                # Например при вводе Сидорова - улица Сидоровой, а не Сидорова
                # Т.к. чаще всего в названиях улиц имена и фамилии фигурируют в радительном падеже,
                # Введенные имена/фамилии переводятся в родительный падеж
                word1 = pymorphy2.MorphAnalyzer().parse(name[0])[0].inflect({'gent'}).word
                word2 = pymorphy2.MorphAnalyzer().parse(name[1])[0].inflect({'gent'}).word
            elif name[0]:
                # Если задано только имя
                word1 = pymorphy2.MorphAnalyzer().parse(name[0])[0].inflect({'gent'}).word
                word2 = ''
            else:
                # Если задана только фамилия
                word1 = pymorphy2.MorphAnalyzer().parse(name[1])[0].inflect({'gent'}).word
                word2 = ''
            # Поиск геокодером именной улицы
            geocoder_request = "http://geocode-maps.yandex.ru/1.x/"
            params = {
                "geocode": 'улица {} {}'.format(word1, word2),
                "format": 'json'
            }
            response = requests.get(geocoder_request, params=params)
            json_response = response.json()
            # Если результат возвращен и улица найдена
            if json_response and json_response["response"]["GeoObjectCollection"]["featureMember"]:
                toponym = json_response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]
                coords = toponym["Point"]["pos"]
                adress = toponym["metaDataProperty"]["GeocoderMetaData"]["Address"]["formatted"]
                if not (word1 in adress.lower() and word1 != '' or word2 in adress.lower() and word2 != ''):
                    # Проверка наличия хотя бы одного из введенных слов в адресе
                    # Без проверки при вводе Максим <Фамилия> выводилась улица Горького,
                    # не совпадавшая ни по имени, ни по фамилии
                    res['response']['text'] = 'По введенным данным не удалось обнаружить географический объект'
                    res['response']['buttons'] = [
                        {
                            'title': 'помощь',
                            'hide': True
                        }
                    ]
                    return
                # Запись координат найденного обекта. Необходима при вызове просмотра карт
                sessionStorage[user_id]['coords'] = coords.split()
                res['response']['buttons'] = [
                    {
                        "title": "Посмотреть гибридную карту",
                        "url": "http://static-maps.yandex.ru/1.x/?ll=" + ','.join(coords.split()) + \
                               "&l=sat,skl&spn=0.0016457,0.000619",
                        "hide": True
                    },
                    {
                        "title": "Посмотреть схематичную карту",
                        "url": "http://static-maps.yandex.ru/1.x/?ll=" + ','.join(coords.split()) + \
                               "&l=map&spn=0.0016457,0.000619",
                        "hide": True
                    },
                    {
                        "title": "Посмотреть спутниковую карту",
                        "url": "http://static-maps.yandex.ru/1.x/?ll=" + ','.join(coords.split()) + \
                               "&l=sat&spn=0.0016457,0.000619",
                        "hide": True
                    },
                    {
                        'title': 'помощь',
                        'hide': True
                    }
                ]
                res['response']['text'] = adress
                return
        if req['request']['command'].lower() in ['пока', "до свидания", "удачи", "прощай"]:
            res['response']['text'] = 'До свидания!'
            res['response']['end_session'] = True
        # Если по по имени/фамилии не нашлось ни улиц, ни других географических объектов
        res['response']['text'] = 'По введенным данным не удалось обнаружить географический объект'
        res['response']['buttons'] = [
            {
                'title': 'помощь',
                'hide': True
            }
        ]
        return


# Функция поиска имени/фамилии в введенном тексте
def get_name(req):
    for entity in req['request']['nlu']['entities']:
        if entity['type'] == 'YANDEX.FIO':
            return entity['value'].get('first_name', None), entity['value'].get('last_name', None)


if __name__ == '__main__':
    app.run()
