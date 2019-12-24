import calendar
import datetime
import locale
import random
import sqlite3
import time
from threading import Thread

import lxml
import requests
import vk_api
from bs4 import BeautifulSoup as bs4
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

existingUsers = []
activeUsers = []

url = "https://edu.tatar.ru/logon"
loginElementName = "main_login"
passwordElementName = "main_password"
successElementText = "Личный кабинет"
wrongElementText = "Неверный логин или пароль. Забыли пароль?"

getStartedKeyboard = VkKeyboard(one_time=False)
getStartedKeyboard.add_button("Начать", color=VkKeyboardColor.PRIMARY)
acceptPrivacyPolicyKeyboard = VkKeyboard(one_time=False)
acceptPrivacyPolicyKeyboard.add_button("Принимаю")

authKeyboard = VkKeyboard(one_time=False)
authKeyboard.add_button("Войти", color=VkKeyboardColor.POSITIVE)

availableCommands = [
    "Начать",
    "Принимаю",
    "Войти",
    "Выйти",
    "Табель успеваемости",
    "Расписание на день",
    "Расписание на неделю",
    "Выйти",
    "Помощь",
    "← Назад",
    "На завтра",
    "На сегодня",
    "На вчера",
    "Клавиатура администратора",
    "Отключить тестовый режим",
    "Включить тестовый режим",
]
admins = ["172244532", "165045139"]


class ThreadWithReturnValue(Thread):
    def __init__(
        self, group=None, target=None, name=None, args=(), kwargs={}, Verbose=None
    ):
        Thread.__init__(self, group, target, name, args, kwargs)
        self._return = None

    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self, *args):
        Thread.join(self, *args)
        return self._return


class Server:
    def __init__(self, token, groupID, databaseName):
        self.token = token
        self.groupID = groupID
        self.databaseName = databaseName
        print("hello message")
        self.loadUsersData()
        

    def connectToVKApi(self):
        vk_session = vk_api.VkApi(token=self.token)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, self.groupID)
        return vk_session, vk, longpoll

    def appendUserToExistingUsersList(self, user):
        if str(user[0]) in admins:
            existingUsers.append(
                Admin(
                    mentionID=user[0],
                    privacyPolicyIsAccepted=user[1],
                    userIsLogged=user[2],
                    userAuthData=user[3],
                )
            )
        else:
            existingUsers.append(
                User(
                    mentionID=user[0],
                    privacyPolicyIsAccepted=user[1],
                    userIsLogged=user[2],
                    userAuthData=user[3],
                )
            )

    def loadUsersData(self):
        print(self.databaseName)
        print(1)
        connect = sqlite3.connect(self.databaseName)
        cursor = connect.cursor()
        userData = cursor.execute("""SELECT * FROM users""").fetchall()
        for user in userData:
            Thread(target=self.appendUserToExistingUsersList, args=(user,)).start()


class User:
    def __init__(
        self,
        mentionID,
        privacyPolicyIsAccepted=False,
        userIsLogged=False,
        getUserAuthDataMode=False,
        userAuthData=None,
        testMode=False,
        ignoreMode=True,
    ):
        self.mentionID = mentionID
        self.privacyPolicyIsAccepted = privacyPolicyIsAccepted
        self.userIsLogged = userIsLogged
        self.getUserAuthDataMode = getUserAuthDataMode
        self.reportCard = {}
        self.session = requests.Session()
        self.session.get(url)
        if userAuthData is not None:
            self.login, self.password = userAuthData.split()
        else:
            self.login = ""
            self.password = ""
        self.wg = False
        self.startTime = 0
        self.ignoreMode = ignoreMode
        self.testMode = testMode
        self.hg = True
        self.btime = 0
        self.schoolCardsKeyboard = VkKeyboard(one_time=False)
        self.schoolCardsKeyboard.add_button(
            "Табель успеваемости", color=VkKeyboardColor.PRIMARY
        )
        self.schoolCardsKeyboard.add_line()
        self.schoolCardsKeyboard.add_button(
            "Расписание на день", color=VkKeyboardColor.PRIMARY
        )
        self.schoolCardsKeyboard.add_line()
        self.schoolCardsKeyboard.add_button("Помощь", color=VkKeyboardColor.POSITIVE)
        self.schoolCardsKeyboard.add_button("Выйти", color=VkKeyboardColor.NEGATIVE)
        self.selectDayKeyboard = VkKeyboard(one_time=False)
        self.selectDayKeyboard.add_button("На завтра", color=VkKeyboardColor.PRIMARY)
        self.selectDayKeyboard.add_line()
        self.selectDayKeyboard.add_button("На сегодня", color=VkKeyboardColor.PRIMARY)
        self.selectDayKeyboard.add_line()
        self.selectDayKeyboard.add_button("На вчера", color=VkKeyboardColor.PRIMARY)
        self.selectDayKeyboard.add_line()
        self.selectDayKeyboard.add_button("← Назад", color=VkKeyboardColor.POSITIVE)

    def callAvailableRequests(self, request):
        availableRequests = {
            "Начать": self.sendIntroductionMessage,
            "Принимаю": self.agreePrivacyPolicy,
            "Войти": self.sendAuthInfoMessage,
            "Табель успеваемости": (
                self.parseReportCard,
                "https://edu.tatar.ru/user/diary/term",
            ),
            "Расписание на день": self.selectDay,
            "← Назад": self.backToMain,
            "На сегодня": (self.parseDay, 0),
            "На вчера": (self.parseDay, -1),
            "На завтра": (self.parseDay, 1),
            "Помощь": self.sendHelpMessage,
            "Выйти": self.logout,
        }

        if self.testMode is False:
            if (
                time.time() - self.startTime > 2 and self.ignoreMode is True
            ) or self.ignoreMode is False:
                if (
                    request == "Табель успеваемости"
                    or request == "На сегодня"
                    or request == "На завтра"
                    or request == "На вчера"
                ):
                    if self.userIsLogged is True or self.userIsLogged == "1":
                        self.checkSessionIsValid()
                        availableRequests[request][0](availableRequests[request][1])
                    else:
                        self.sendAuthInfoMessage()
                else:
                    availableRequests[request]()
                    self.wg = True
            else:
                if self.wg is True:
                    vk.messages.send(
                        peer_id=self.mentionID,
                        message="Ты слишком часто отправляешь команды. Я буду игнорировать тебя в течение 5 секунд.",
                        random_id=random.getrandbits(32),
                    )
                    self.wg = False
        else:
            if self.hg is True:
                vk.messages.send(
                    peer_id=self.mentionID,
                    message="Ой, ты не входишь в программу тестирования этого бота. \n \n Как только бот выйдет из закрытого тестирования, мы сразу скажем тебе об этом.",
                    random_id=random.getrandbits(32),
                )
                self.hg = False

    def logout(self):
        self.editUsersData("setUserIsLoggedFlag", flag=False)
        self.editUsersData("setUserAuthData", flag=False)
        self.userIsLogged = False
        vk.messages.send(
            peer_id=self.mentionID,
            message=f"Вы успешно вышли. \n Логин: {self.login} \n Пароль: {self.password}",
            random_id=random.getrandbits(32),
            keyboard=authKeyboard.get_keyboard(),
        )
        self.login = ""
        self.password = ""
        self.session = requests.Session()
        self.session.get(url)

    def sendHelpMessage(self):
        vk.messages.send(
            peer_id=self.mentionID,
            message="Все доступные команды бота: (https://vk.com/@educheck-help)",
            random_id=random.getrandbits(32),
        )

    def getUserAuthData(self, request):
        login, password = request.split()
        self.auth(login=login, password=password, hideMode=False)

    def sendAuthInfoMessage(self):
        if (
            self.privacyPolicyIsAccepted is True or self.privacyPolicyIsAccepted == "1"
        ) and (self.userIsLogged == "0" or self.userIsLogged is False):
            vk.messages.send(
                peer_id=self.mentionID,
                message="Введи логин и пароль через пробел. \n Пример: 1234567890 QWERTY",
                random_id=random.getrandbits(32),
            )
            self.getUserAuthDataMode = True
        elif (
            self.privacyPolicyIsAccepted is True or self.privacyPolicyIsAccepted == "1"
        ) and (self.userIsLogged == "1" or self.userIsLogged is True):
            vk.messages.send(
                peer_id=self.mentionID,
                message="Ты уже вошёл в свой аккаунт. Хотите выйти? Нажмите на кнопку 'Выйти'.",
                random_id=random.getrandbits(32),
            )
        elif (
            self.privacyPolicyIsAccepted == "0" or self.privacyPolicyIsAccepted is False
        ):
            vk.messages.send(
                peer_id=self.mentionID,
                message="Ты ещё не принял условия Политики конфиденциальности.",
                random_id=random.getrandbits(32),
            )
            self.sendPrivacyPolicyMessage()

    def sendPrivacyPolicyMessage(self):
        vk.messages.send(
            peer_id=self.mentionID,
            message="Нажми на кнопку 'Принимаю' или напиши сам, чтобы принять условия Политики конфиденциальности",
            random_id=random.getrandbits(32),
            keyboard=acceptPrivacyPolicyKeyboard.get_keyboard(),
        )

    def sendIntroductionMessage(self):
        if self.privacyPolicyIsAccepted is False or self.privacyPolicyIsAccepted == "0":
            vk.messages.send(
                peer_id=self.mentionID,
                message="Привет! Мы ценим конфиденциальность пользовательских данных, поэтому предалагаем тебе прочитать Политику конфиденциальности (vk.com/@educheck-privacy-policy) нашего бота и принять её условия.",
                random_id=random.getrandbits(32),
            )
            self.sendPrivacyPolicyMessage()
        else:
            if self.userIsLogged is True or self.userIsLogged == "1":
                vk.messages.send(
                    peer_id=self.mentionID,
                    message="Ты уже можешь пользоваться мною (открой клавиатуру)",
                    random_id=random.getrandbits(32),
                    keyboard=self.schoolCardsKeyboard.get_keyboard(),
                )
            if self.userIsLogged is False or self.userIsLogged == "0":
                vk.messages.send(
                    peer_id=self.mentionID,
                    message="Тебе осталось всего лишь войти!",
                    random_id=random.getrandbits(32),
                    keyboard=authKeyboard.get_keyboard(),
                )

    def sendAfterAuthMessage(self, flag):
        if flag is True:
            vk.messages.send(
                peer_id=self.mentionID,
                message=f"Авторизация пройдена успешно. \n Логин: {self.login} \n Пароль: {self.password}",
                random_id=random.getrandbits(32),
                keyboard=self.schoolCardsKeyboard.get_keyboard(),
            )
        else:
            vk.messages.send(
                peer_id=self.mentionID,
                message="Ты ввел неверный логин или пароль. \n \n Введи логин и пароль ещё раз, если ты снова хочешь попробовать войти.",
                random_id=random.getrandbits(32),
            )

    def agreePrivacyPolicy(self):
        if self.privacyPolicyIsAccepted is True or self.privacyPolicyIsAccepted == "1":
            vk.messages.send(
                peer_id=self.mentionID,
                message="Не надо. Ты уже принял Политику конфиденциальности нашего бота",
                random_id=random.getrandbits(32),
            )
        else:
            self.privacyPolicyIsAccepted = True
            self.editUsersData("setPrivacyPolicyIsAcceptedFlag")
            vk.messages.send(
                peer_id=self.mentionID,
                message="Список доступных команд (vk.com/@educheck-help)",
                random_id=random.getrandbits(32),
            )
            vk.messages.send(
                peer_id=self.mentionID,
                message="Ура! Теперь ты можешь пользоваться нашим ботом. \n Нажми на кнопку 'Войти', чтобы ввести свои данные",
                random_id=random.getrandbits(32),
                keyboard=authKeyboard.get_keyboard(),
            )

    def editUsersData(self, type, login=None, password=None, flag=None):
        connect = sqlite3.connect(server.databaseName)
        cursor = connect.cursor()
        availableDatabaseEditingTypes = {
            "setPrivacyPolicyIsAcceptedFlag": self.setPrivacyPolicyIsAcceptedFlag,
            "setUserIsLoggedFlag": self.setUserIsLoggedFlag,
            "addNewUserData": self.addNewUserData,
            "setUserAuthData": self.setUserAuthData,
        }
        if login is not None and password is not None:
            availableDatabaseEditingTypes[type](connect, cursor, login, password)
        elif type == "setUserIsLoggedFlag" or type == "setUserAuthData":
            availableDatabaseEditingTypes[type](connect, cursor, flag)
        else:
            availableDatabaseEditingTypes[type](connect, cursor)

    def setPrivacyPolicyIsAcceptedFlag(self, connect, cursor, flag=True):
        cursor.execute(
            f"""UPDATE users SET privacyPolicyIsAccepted = {flag} WHERE id = {self.mentionID}"""
        )
        connect.commit()

    def setUserIsLoggedFlag(self, connect, cursor, flag):
        cursor.execute(
            f"""UPDATE users SET userIsLogged = {flag} WHERE id = {self.mentionID}"""
        )
        connect.commit()

    def setUserAuthData(self, connect, cursor, flag):
        if flag is True:
            aData = f"{self.login} {self.password}"
            cursor.execute(
                f"""UPDATE users SET authData = ? WHERE id = {self.mentionID}""",
                (aData,),
            )
        else:
            cursor.execute(
                f"""UPDATE users SET authData = ? WHERE id = {self.mentionID}""",
                (None,),
            )
        connect.commit()

    def addNewUserData(self, connect, cursor):
        cursor.execute(
            f"""INSERT OR IGNORE INTO users(id, privacyPolicyIsAccepted, userIsLogged) VALUES({self.mentionID}, {'False'}, {'False'})"""
        )
        connect.commit()

    def checkSessionIsValid(self):
        if time.time() - self.btime > 30:
            response = self.session.get(
                "https://edu.tatar.ru/user/diary/term", allow_redirects=False
            )
            if response.status_code != 200:
                self.auth(self.login, self.password, hideMode=True)

    def auth(self, login, password, hideMode):
        cookie = {
            "_ga": "GA1.2.1804685607.1574325953",
            "_gid": "GA1.2.1116002961.1574325953",
        }
        data = {loginElementName: login, passwordElementName: password}
        headers = {"Referer": url}
        RH = self.session.post(url, data=data, cookies=cookie, headers=headers).text
        soup = bs4(RH, "lxml")
        if hideMode is False:
            if soup.h2.text.strip() == successElementText:
                self.login = login
                self.password = password
                self.getUserAuthDataMode = False
                self.userIsLogged = True
                self.editUsersData("setUserIsLoggedFlag", flag=True)
                self.editUsersData("setUserAuthData", flag=True)
                self.sendAfterAuthMessage(True)
                self.btime = time.time()
            else:
                self.sendAfterAuthMessage(False)

    def parseReportCard(self, URL):
        self.reportCard = {}
        self.startTime = time.time()
        today = time.time()
        RH = self.session.get(URL).text
        soup = bs4(RH, "lxml")
        soup = soup.find("table").findAll("td")
        resultTags = [
            tag.text
            for tag in soup
            if ("colspan" in tag.attrs)
            or tag.string is not None
            and tag.text != "\n"
            and tag.text != "просмотр"
            and tag.text.strip() != "—"
        ][4::]
        for index, item in enumerate(resultTags, 1):
            if item.isdigit():
                item = int(item)
                self.reportCard[subjectName].append(item)
            else:
                try:
                    item = float(item)
                    self.reportCard[subjectName].append(item)
                except:
                    self.reportCard[item] = []
                    subjectName = item
        for subject, marks in self.reportCard.items():
            if len(marks) >= 3:
                if isinstance(marks[-2], float) is True:
                    self.reportCard[subject][
                        -2
                    ] = f"средний балл: {self.reportCard[subject][-2]}"
                    self.reportCard[subject][
                        -1
                    ] = f"итоговый балл: {int(self.reportCard[subject][-1])}"
                else:
                    self.reportCard[subject][
                        -1
                    ] = f"средний балл: {self.reportCard[subject][-1]}"

        self.returnContent()

    def selectDay(self):
        vk.messages.send(
            peer_id=self.mentionID,
            message="Выбери подходящий тебе день:",
            random_id=random.getrandbits(32),
            keyboard=self.selectDayKeyboard.get_keyboard(),
        )

    def backToMain(self):
        vk.messages.send(
            peer_id=self.mentionID,
            message="Ты вернулся назад.",
            random_id=random.getrandbits(32),
            keyboard=self.schoolCardsKeyboard.get_keyboard(),
        )

    def parseDay(self, URL):
        if URL == 0:
            URL = f"https://edu.tatar.ru/user/diary/day?for={str(time.time()).split('.')[0]}"
        elif URL == 1:
            URL = f"https://edu.tatar.ru/user/diary/day?for={int(str(time.time()).split('.')[0]) + 86400}"
        elif URL == -1:
            URL = f"https://edu.tatar.ru/user/diary/day?for={int(str(time.time()).split('.')[0]) - 86400}"

        self.startTime = time.time()
        self.reportCard = {}
        p = []
        resultTags = []
        resultString = ""
        RH = self.session.get(URL).text
        soup = bs4(RH, "lxml")
        soup = soup.find("tbody").findAll("td")
        for tag in soup:
            if "title" in tag.attrs:
                resultTags.append(tag.get("title"))
            else:
                resultTags.append(tag.text.replace("\n", ""))
        resultTags = list(reversed(resultTags))
        self.reportCard[
            time.strftime("%a, %d %b %Y", time.localtime(int(URL.split("=")[1])))
        ] = []
        for tag in resultTags:
            if len(tag.split("—")) == 2 and tag.count(":") == 2:
                p.append(tag)
                self.reportCard[
                    time.strftime(
                        "%a, %d %b %Y", time.localtime(int(URL.split("=")[1]))
                    )
                ].append(list(reversed(p)))
                p = []
            else:
                if len(tag) != 0:
                    tag = tag.strip()
                if tag.isdigit() is True and len(tag) >= 2:
                    tag = ", ".join(list(tag))
                p.append(tag)
        if len(list(self.reportCard.values())[0]) == 0:
            vk.messages.send(
                peer_id=self.mentionID,
                message="Ой, мы ничего не смогли найти... \n Возможно, сегодня или завтра выходной день? \n \n Если это не так, напиши, пожалуйста, в техническую поддержку.",
                random_id=random.getrandbits(32),
            )
        else:
            resultString += list(self.reportCard.keys())[0] + "\n \n"
            for index, subject in enumerate(
                list(reversed(list(self.reportCard.values())[0])), 1
            ):
                if len(subject) == 6:
                    resultString += f"{index}. Время: {subject[0]} \n Предмет: {subject[1]} \n Что задали: {subject[2]} \n Комментарий: {subject[3]} \n Оценка: {', '.join([subject[4], subject[5]])} \n \n"
                else:
                    resultString += f"{index}. Время: {subject[0]} \n Предмет: {subject[1]} \n Что задали: {subject[2]} \n Комментарий: {subject[3]} \n Оценка: {subject[4]} \n \n"
            vk.messages.send(
                peer_id=self.mentionID,
                message=resultString,
                random_id=random.getrandbits(32),
            )

    def returnContent(self):
        try:
            resultString = ""
            for subject, marks in self.reportCard.items():
                if len(marks) == 0:
                    resultString += f"{subject}: — \n \n"
                elif subject == "ИТОГО":
                    resultString += f"Средний балл: {marks[0]}, итоговая оценка: {marks[3].split(': ')[1]}"
                else:
                    resultString += (
                        f"{subject}: {', '.join([str(mark) for mark in marks])} \n \n"
                    )
            if len(resultString) == 0:
                raise
            else:
                vk.messages.send(
                    peer_id=self.mentionID,
                    message=resultString,
                    random_id=random.getrandbits(32),
                )
        except:
            vk.messages.send(
                peer_id=self.mentionID,
                message="Не удалось получить необходимые данные. Попробуй ещё раз.",
                random_id=random.getrandbits(32),
            )

    def __str__(self):
        return str(self.mentionID)

    def __repr__(self):
        return str(self.mentionID)

    def __eq__(self, other):
        if self.mentionID == other.mentionID:
            return True
        else:
            return False

    def __ne__(self, other):
        if self.mentionID != other.mentionID:
            return True
        else:
            return False

    def __lt__(self, other):
        if self.mentionID < other.mentionID:
            return True
        else:
            return False

    def __gt__(self, other):
        if self.mentionID > other.mentionID:
            return True
        else:
            return False

    def __le__(self, other):
        if self.mentionID <= other.mentionID:
            return True
        else:
            return False

    def __ge__(self, other):
        if self.mentionID >= other.mentionID:
            return True
        else:
            return False


class Admin(User):
    def __init__(
        self,
        mentionID,
        privacyPolicyIsAccepted=False,
        userIsLogged=False,
        getUserAuthDataMode=False,
        userAuthData=None,
        testMode=False,
        ignoreMode=False,
    ):
        super().__init__(
            mentionID=mentionID,
            privacyPolicyIsAccepted=privacyPolicyIsAccepted,
            userIsLogged=userIsLogged,
            getUserAuthDataMode=getUserAuthDataMode,
            userAuthData=userAuthData,
            testMode=testMode,
            ignoreMode=ignoreMode,
        )
        self.schoolCardsKeyboard.add_line()
        self.schoolCardsKeyboard.add_button(
            "Клавиатура администратора", color=VkKeyboardColor.PRIMARY
        )
        self.adminKeyboard = VkKeyboard(one_time=False)
        self.adminKeyboard.add_button(
            "Отключить тестовый режим", color=VkKeyboardColor.PRIMARY
        )
        self.adminKeyboard.add_button(
            "Включить тестовый режим", color=VkKeyboardColor.PRIMARY
        )
        self.adminKeyboard.add_line()
        self.adminKeyboard.add_button("← Назад", color=VkKeyboardColor.POSITIVE)

    def callAvailableRequests(self, request):
        availableRequests = {
            "Начать": self.sendIntroductionMessage,
            "Принимаю": self.agreePrivacyPolicy,
            "Войти": self.sendAuthInfoMessage,
            "Табель успеваемости": (
                self.parseReportCard,
                "https://edu.tatar.ru/user/diary/term",
            ),
            "Расписание на день": self.selectDay,
            "← Назад": self.backToMain,
            "На сегодня": (
                self.parseDay,
                f"https://edu.tatar.ru/user/diary/day?for={str(time.time()).split('.')[0]}",
            ),
            "На вчера": (
                self.parseDay,
                f"https://edu.tatar.ru/user/diary/day?for={int(str(time.time()).split('.')[0]) - 86400}",
            ),
            "На завтра": (
                self.parseDay,
                f"https://edu.tatar.ru/user/diary/day?for={int(str(time.time()).split('.')[0]) + 86400}",
            ),
            "Выйти": self.logout,
            "Помощь": self.sendHelpMessage,
            "Клавиатура администратора": self.getAdminKeyboard,
            "Отключить тестовый режим": self.deactivateTestMode,
            "Включить тестовый режим": self.activateTestMode,
        }

        if self.testMode is False:
            if (
                time.time() - self.startTime > 5 and self.ignoreMode is True
            ) or self.ignoreMode is False:
                if (
                    request == "Табель успеваемости"
                    or request == "На сегодня"
                    or request == "На завтра"
                    or request == "На вчера"
                ):
                    if self.userIsLogged is True or self.userIsLogged == "1":
                        self.checkSessionIsValid()
                        availableRequests[request][0](availableRequests[request][1])
                    elif self.userIsLogged is False or self.userIsLogged == "0":
                        self.sendAuthInfoMessage()
                else:
                    availableRequests[request]()
                    self.wg = True
            else:
                if self.wg is True:
                    vk.messages.send(
                        peer_id=self.mentionID,
                        message="Ты слишком часто отправляешь команды. Я буду игнорировать тебя в течение 5 секунд.",
                        random_id=random.getrandbits(32),
                    )
                    self.wg = False
        else:
            if self.hg is True:
                vk.messages.send(
                    peer_id=self.mentionID,
                    message="Ой, ты не входишь в программу тестирования этого бота. \n \n Как только бот выйдет из закрытого тестирования, мы сразу скажем тебе об этом.",
                    random_id=random.getrandbits(32),
                )
                self.hg = False

    def getAdminKeyboard(self):
        vk.messages.send(
            peer_id=self.mentionID,
            message="Клавиатура администратора:",
            random_id=random.getrandbits(32),
            keyboard=self.adminKeyboard.get_keyboard(),
        )

    def deactivateTestMode(self):
        for user in existingUsers:
            user.testMode = False
        vk.messages.send(
            peer_id=self.mentionID,
            message="Тестовый режим отключен для всех зарегистрированных пользователей.",
            random_id=random.getrandbits(32),
            keyboard=self.adminKeyboard.get_keyboard(),
        )

    def activateTestMode(self):
        for user in existingUsers:
            if str(user.mentionID) not in admins:
                user.testMode = True
                user.hg = True
        vk.messages.send(
            peer_id=self.mentionID,
            message="Тестовый режим включен для всех зарегистрированных пользователей.",
            random_id=random.getrandbits(32),
            keyboard=self.adminKeyboard.get_keyboard(),
        )

    def backToMain(self):
        vk.messages.send(
            peer_id=self.mentionID,
            message="Ты вернулся назад.",
            random_id=random.getrandbits(32),
            keyboard=self.schoolCardsKeyboard.get_keyboard(),
        )

    def sendNotififactionMessage(self):
        for user in existingUsers:
            time.sleep(5)
            vk.messages.send(
                peer_id=user.mentionID,
                message="Мы вышли из режима тестирования, теперь ты можешь пользоваться ботом!",
                random_id=random.getrandbits(32),
            )


server = Server(
    token="855c82e1ca471b9af66fdb369be1e59d6d8233f93d361126c4eebf228d44dc7f4d4169498b062b90c9fa9",
    groupID="188029668",
    databaseName="usersDB.db",
)
vk_session, vk, longpoll = server.connectToVKApi()


def userIsExisting(mentionID):
    if len(existingUsers) != 0:
        for user in existingUsers:
            if str(user.mentionID) == str(mentionID):
                return user
    if str(mentionID) in admins:
        user = Admin(mentionID=mentionID)
    else:
        user = User(mentionID=mentionID)
    user.editUsersData("addNewUserData")
    existingUsers.append(user)
    return user


def eventHandler(event):
    try:
        if event.type == VkBotEventType.GROUP_JOIN:
            vk.messages.send(
                peer_id=event.obj["user_id"],
                message=f"Привет, {vk.users.get(user_ids=event.obj['user_id'])[0]['first_name']} \n Мы рады, что ты подписался на нас. \n \n Нажми на кнопку 'Начать', чтобы начать пользоваться нашим ботом.",
                random_id=random.getrandbits(32),
                keyboard=getStartedKeyboard.get_keyboard(),
            )
            any_vk.status.set(
                text=f"С нами уже {any_vk.groups.getMembers(group_id=188029668)['count']} человек",
                group_id=188029668,
            )
        elif event.type == VkBotEventType.GROUP_LEAVE:
            vk.messages.send(
                peer_id=event.obj["user_id"],
                message=f"Пока, {vk.users.get(user_ids=event.obj['user_id'])[0]['first_name']}. \n Мы будем скучать по тебе!",
                random_id=random.getrandbits(32),
                keyboard=getStartedKeyboard.get_keyboard(),
            )
            any_vk.status.set(
                text=f"С нами уже {any_vk.groups.getMembers(group_id=188029668)['count']} человек",
                group_id=188029668,
            )
        elif event.type == VkBotEventType.MESSAGE_NEW:
            thread = ThreadWithReturnValue(
                target=userIsExisting, args=(event.obj.message["from_id"],)
            )
            thread.start()
            user = thread.join()
            if event.obj.message["text"] in availableCommands:
                Thread(
                    target=user.callAvailableRequests, args=(event.obj.message["text"],)
                ).start()
            if user.getUserAuthDataMode is True:
                user.getUserAuthData(event.obj.message["text"])
    except:
        pass


for event in longpoll.listen():
    try:
        Thread(target=eventHandler, args=(event,)).start()
    except:
        pass
