zhime 智慧注音 — 安裝說明
==========================

【重要】PIME 要自己先安裝，這個 zip 裡面沒有附 PIME。
       zhime 是在 PIME（開源 Windows 輸入法框架）上跑的輸入法。

1. 安裝 PIME
   到 https://github.com/EasyIME/PIME/releases
   下載 PIME-1.3.0-stable-setup.exe 並安裝。
   新酷音等其他輸入法不需要的話，可以在安裝畫面取消勾選。

2. 把這個 zip 整個解壓縮（不要在 zip 裡直接點開）。

3. 雙擊「安裝.bat」，在 UAC 視窗按「是」。
   出現「Windows 已保護您的電腦」時，請按「其他資訊」→「仍要執行」。

4. 按 Win + Space 切換到「智慧注音 (zhime)」。
   第一次打字要等幾秒，讓它載入模型。

不需要另外安裝 Python。

按鍵
----
  注音／英文字母／空白鍵   輸入（空白鍵是一聲）
  Shift + 字母             大寫英文
  Enter                    送出選中的候選
  ↓ → Tab / ↑ ← Shift+Tab  選下一個／上一個候選
  Ctrl + 1~9               直接送出第 N 個候選
  Backspace / Esc          刪一個鍵／取消
  Shift + 標點             全形標點

解除安裝
--------
雙擊「解除安裝.bat」。

專案首頁與原始碼：https://github.com/Buddy-Lu/zhime
授權：見 LICENSE 與 NOTICE.txt
