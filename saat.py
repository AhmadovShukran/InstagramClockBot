from tkinter import *
from selenium import webdriver
import random
import time
from PIL import Image,ImageDraw,ImageFont
from selenium.webdriver.firefox.options import Options
import os
pencere=Tk()
options=Options()
options.add_argument("--headless")
pencere.title("Sign In")
pencere.geometry("505x300")
pencere.resizable(FALSE,FALSE)
pencere.configure(bg="#19193a")
sign=Label(text="Sign In",bg="#19193a",font="Impact 28",fg="white")
sign.place(x=200,y=0)
usernames=Label(text="Username",fg="white",font="Fixedsys 14",bg="#19193a")
usernames.place(x=30,y=65)
usernamess=Entry(width=40,font="Impact 16")
usernamess.place(x=32,y=100)
passwords=Label(text="Password",fg="white",font="Fixedsys 14",bg="#19193a")
passwords.place(x=30,y=145)
passwordss=Entry(width=40,show="●",font="Impact 16")
passwordss.place(x=30,y=180)
def giris():
    pencere.withdraw()
    path = (str(os.getcwd())+"\\geckodriver.exe")
    browser = webdriver.Firefox(executable_path=path,options=options)
    browser.get("https://www.instagram.com/accounts/edit")
    time.sleep(5)
    while True:
        try:
            browser.find_element_by_name("username")
            browser.find_element_by_name("password")
            browser.find_element_by_xpath("//*[@id='react-root']/section/main/div/article/div/div[1]/div/form/div[4]/button/div")
            break
        except:
            print("-")
            time.sleep(3)
    browser.find_element_by_name("username").send_keys(usernamess.get())
    browser.find_element_by_name("password").send_keys(passwordss.get())
    browser.find_element_by_xpath("//*[@id='react-root']/section/main/div/article/div/div[1]/div/form/div[4]/button/div").click()

    time.sleep(5)
    while True:
        sen=0
        try:          
            sekilli = browser.find_element_by_xpath('//input[@type="file"]')
            break
        except:
            print("Tapilmadi")
            time.sleep(3)
            continue
    sekilli = browser.find_element_by_xpath('//input[@type="file"]')
    print("Hesaba Daxil Oldu")
    while True:
        a = time.strftime("%H:%M")
        b = time.strftime("%d-%b-%y")
        rengler=["#0200fe","#7000fe","#10f21c","#ff15f8","#eefe05","#fa116b","#9B2335","#E08119","#F96714","#00539C","#00A591","#006E51"]
        reng=random.choice(rengler)
        font_novu = ImageFont.truetype("tcceb.ttf", 27)
        font_novu1 = ImageFont.truetype("tcceb.ttf", 50)
        sekil=Image.new("RGBA",(150,150),reng)
        yazmaq = ImageDraw.Draw(sekil)
        yazmaq.text(xy=(17, 37,), text=a, fill="White", font=font_novu1)
        yazmaq.text(xy=(22, 83,), text=b, fill="White", font=font_novu)
        sekil.save(str(os.getcwd())+r"\goz.png")
        sekilli.send_keys((str(os.getcwd())+r"\goz.png"))
        sen=sen+1
        print("Sekil Deyisdi. "+"N: "+str(sen))
        print("Indi Saat==>  "+str(a))
        time.sleep(15)
signing=Button(width=44,text="Sign In",fg="white",bg="red",command=giris,font="Impact 16")
signing.place(x=28,y=235)
pencere.mainloop()
