# zhime 智慧注音

打錯字也猜得出來的 Windows 注音輸入法，中英文不用切換。

- **容錯**：按到隔壁鍵、漏打聲調、多打或少打一個鍵、兩個鍵順序打反，它都會照「你本來想打的」去猜。
  例如把「等我一下」打成 `2/3ji3i vu84`，一樣會得到 等我一下。
- **中英混打**：直接打 `ji3au/6wu0 u.3meeting` 就會得到「我明天有meeting」，不用按 Shift 切換。
- **選字列**：最可能的句子直接顯示在游標處，其他候選排成一列，類似 iPhone 的選字方式。
- **離線、只用 CPU**：每打一個鍵約 26 ms，不用顯示卡，也不會上傳任何東西。

## 實測準確率

測試資料是 500 句 Common Voice 台灣華語句子，調參數時沒有用到這些句子。

| 每句打錯幾個鍵 | 整句全對（第一候選） | 正確答案在前 5 個候選 | 字正確率 |
|---|---|---|---|
| 0 | 80.4% | 94.0% | 96.3% |
| 1 | 74.8% | 91.0% | 94.8% |
| 2 | 65.8% | 84.0% | 92.6% |

## 安裝

> [!IMPORTANT]
> **PIME 要自己先安裝。Release 的 zip 裡面沒有附 PIME。**
> zhime 是 [PIME](https://github.com/EasyIME/PIME)（開源的 Windows 輸入法框架）上的一個輸入法，沒有先裝 PIME 就無法安裝 zhime。

1. **安裝 PIME**：到 [PIME Releases](https://github.com/EasyIME/PIME/releases) 下載 `PIME-1.3.0-stable-setup.exe` 並安裝。
   安裝畫面會預設勾選新酷音等其他輸入法，不需要的話可以取消勾選，zhime 不需要它們。
2. **下載 zhime**：到本專案的 [Releases](../../releases) 下載 `zhime-<版本>-win64.zip`，然後**整個解壓縮**。不要在 zip 裡直接點開。
3. **執行安裝**：雙擊解壓縮後資料夾裡的 `安裝.bat`，在 UAC 視窗按「是」。
   - 出現藍色的「Windows 已保護您的電腦」視窗（SmartScreen）時，按「其他資訊」→「仍要執行」。會出現這個視窗是因為本程式沒有付費購買程式碼簽章。
   - 安裝程式會自動把「智慧注音 (zhime)」加入你的鍵盤清單。
4. **開始使用**：按 `Win + Space` 切換到「智慧注音 (zhime)」。第一次打字要等幾秒，讓它載入模型。

安裝包已經內含執行需要的 Python，**不需要另外安裝 Python**。安裝後的檔案在 `C:\Program Files (x86)\PIME\zhime\`。

### 解除安裝
雙擊同一個資料夾裡的 `解除安裝.bat`。如果 PIME 裡已經沒有其他輸入法，可以再到「設定 > 應用程式」移除 PIME。

## 按鍵

| 按鍵 | 作用 |
|---|---|
| 注音鍵、英文字母、空白鍵 | 輸入（空白鍵是一聲） |
| Shift + 字母 | 大寫英文 |
| Enter | 送出目前選中的候選字 |
| ↓ / → / Tab | 選下一個候選 |
| ↑ / ← / Shift+Tab | 選上一個候選 |
| Ctrl + 1~9 | 直接送出第 N 個候選 |
| Backspace | 刪掉最後一個鍵 |
| Esc | 取消整串輸入 |
| Shift + 標點 | 全形標點（，。？：、！「」（）） |

zhime 會記住你常選的詞，存在 `%APPDATA%\zhime\user_words.json`。

## 運作方式

1. 用 weighted edit distance 把按鍵序列對到所有合法注音音節，並考慮鍵盤上的相鄰鍵、聲調混淆、ㄓ/ㄗ 之類的發音混淆。
2. 查詞庫，把音節組成可能的詞。
3. 用 word bigram 語言模型做 beam search，選出最通順、也最符合你打的鍵的句子。
   這個模型是用 2.24 億詞的 PTT 文章加上中文維基百科訓練的 Kneser-Ney 模型。
4. 英文單字用 wordfreq 的詞頻，加上拼錯一個字母的修正。

程式碼在 `src/zhime/`：

| 檔案 | 內容 |
|---|---|
| `keyboard.py` | 大千鍵盤配置與錯字成本 |
| `decoder.py` | 解碼器 |
| `english.py` | 英文處理 |
| `ngram.py` | 語言模型 |
| `engine.py` | 輸入狀態 |

PIME 端的程式在 `pime_backend/`。

## 從原始碼建置

需要 [uv](https://docs.astral.sh/uv/)。

```powershell
git clone https://github.com/Buddy-Lu/zhime && cd zhime
uv sync --extra build

# 詞庫：McBopomofo 的 data.txt（第一次載入時會自動轉成 data/lexicon.pkl）
git clone --depth 1 --filter=blob:none --sparse https://github.com/openvanilla/McBopomofo third_party/McBopomofo
git -C third_party/McBopomofo sparse-checkout set Source/Data
uv run python -c "from zhime.lexicon import Lexicon; Lexicon.load()"

# 語言模型：下載 PTT + 維基百科並統計，輸出 data/bigram.pkl（要跑一段時間）
uv run python -m zhime.ngram build

# 打包成 dist/zhime-<版本>-win64.zip
pwsh -File install/build_release.ps1

# 不經過 Windows，直接用 PIME 的協定測試打包好的版本
uv run python tests_pime_sim.py dist/zhime-0.1.0-win64/zhime/python/python.exe dist/zhime-0.1.0-win64/zhime
```

想重跑準確率評估，還需要 Common Voice 的句子，放在 `third_party/common-voice/server/data/zh-TW`。評估指令是 `uv run python -m zhime.evaluate --split test`。

另外有一個可選的 Qwen3-0.6B 重新排序器：先執行 `uv sync --extra rerank`，再設定環境變數 `ZHIME_RERANK=1`。它比較慢，準確率也沒有比預設的模型好，所以預設是關閉的。

## 授權

zhime 的程式碼採用 MIT 授權。第三方程式與資料（PIME、McBopomofo、wordfreq、PTT 資料集、維基百科）各自的授權請見 [NOTICE.txt](NOTICE.txt)。
