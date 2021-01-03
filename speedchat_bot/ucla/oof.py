import imgkit
import os

print(os.listdir())

css = 'oof.css'

imgkit.from_file('speedchat_bot/ucla/oof.html', 'out.jpg', css=css)
