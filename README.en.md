English | [中文](README.md)

# zhime — Smart Zhuyin IME

A Zhuyin (Bopomofo) input method for Windows that figures out what you meant even when you mistype, and lets you mix Chinese and English without switching modes.

- **Typo-tolerant**: it decodes what you *meant* to type even if you hit a neighbouring key, drop a tone, add or miss a key, or swap two keys.
  For example, typing 等我一下 as `2/3ji3i vu84` still gives 等我一下.
- **Mixed Chinese/English**: just type `ji3au/6wu0 u.3meeting` and get 我明天有meeting — no Shift toggling.
- **Candidate bar**: the most likely sentence appears inline at the cursor, with alternatives in one row underneath, iPhone-style.
- **Offline, CPU only**: about 26 ms per keystroke. It needs no GPU and uploads nothing.

## Measured accuracy

The test set is 500 Taiwanese Mandarin sentences from Common Voice. None of them were used while tuning.

| Typos per sentence | Whole sentence right (top candidate) | Right answer in top 5 | Character accuracy |
|---|---|---|---|
| 0 | 80.4% | 94.0% | 96.3% |
| 1 | 74.8% | 91.0% | 94.8% |
| 2 | 65.8% | 84.0% | 92.6% |

## Installation

> [!IMPORTANT]
> **You must install PIME yourself. The release zip does NOT include PIME.**
> zhime is an input method that runs on [PIME](https://github.com/EasyIME/PIME), an open-source Windows IME framework. You cannot install zhime without PIME.

1. **Install PIME**: download `PIME-1.3.0-stable-setup.exe` from [PIME Releases](https://github.com/EasyIME/PIME/releases) and install it.
   The installer pre-selects other input methods such as 新酷音 (Chewing). You can untick them; zhime does not need them.
2. **Download zhime**: get `zhime-<version>-win64.zip` from this project's [Releases](../../releases), then **extract the whole zip**. Don't run files from inside the zip.
3. **Install**: double-click `安裝.bat` (Install) in the extracted folder and click "Yes" in the UAC prompt.
   - If a blue "Windows protected your PC" (SmartScreen) window appears, click "More info" → "Run anyway". It appears because the program isn't signed with a paid code-signing certificate.
   - The installer adds 智慧注音 (zhime) to your keyboard list automatically.
4. **Use it**: press `Win + Space` and switch to 智慧注音 (zhime). The first keystroke takes a few seconds while the model loads.

The package bundles the Python it needs, so **you don't need to install Python**. Installed files go to `C:\Program Files (x86)\PIME\zhime\`.

### Uninstall
Double-click `解除安裝.bat` (Uninstall) in the same folder. If PIME has no other input methods left, you can also remove PIME from Settings > Apps.

## Keys

| Key | Action |
|---|---|
| Zhuyin keys, letters, Space | Type (Space is tone 1) |
| Shift + letter | Uppercase English |
| Enter | Commit the highlighted candidate |
| ↓ / → / Tab | Next candidate |
| ↑ / ← / Shift+Tab | Previous candidate |
| Ctrl + 1–9 | Commit candidate N directly |
| Backspace | Delete the last key |
| Esc | Cancel the whole input |
| Shift + punctuation | Full-width punctuation (，。？：、！「」（）) |

zhime remembers the words you pick often and stores them in `%APPDATA%\zhime\user_words.json`.

## How it works

1. A weighted edit distance matches the keystrokes against every valid Zhuyin syllable. It accounts for neighbouring keys, tone mix-ups, and sound confusions such as ㄓ/ㄗ.
2. A lexicon lookup turns the syllables into candidate words.
3. A beam search with a word bigram language model picks the sentence that both reads most naturally and best fits the keys you typed.
   The model is a Kneser-Ney model trained on 224 million words of PTT posts and Chinese Wikipedia.
4. English words come from wordfreq word frequencies, with one-letter misspelling correction.

The code is in `src/zhime/`:

| File | Contents |
|---|---|
| `keyboard.py` | Daqian keyboard layout and typo costs |
| `decoder.py` | The decoder |
| `english.py` | English handling |
| `ngram.py` | The language model |
| `engine.py` | Input session state |

The PIME side lives in `pime_backend/`.

## Building from source

Requires [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/Buddy-Lu/zhime && cd zhime
uv sync --extra build

# Lexicon: McBopomofo's data.txt (converted to data/lexicon.pkl on first load)
git clone --depth 1 --filter=blob:none --sparse https://github.com/openvanilla/McBopomofo third_party/McBopomofo
git -C third_party/McBopomofo sparse-checkout set Source/Data
uv run python -c "from zhime.lexicon import Lexicon; Lexicon.load()"

# Language model: downloads PTT + Wikipedia and counts them into data/bigram.pkl (takes a while)
uv run python -m zhime.ngram build

# Package as dist/zhime-<version>-win64.zip
pwsh -File install/build_release.ps1

# Test the packaged build over the PIME protocol, without going through Windows
uv run python tests_pime_sim.py dist/zhime-0.1.0-win64/zhime/python/python.exe dist/zhime-0.1.0-win64/zhime
```

To rerun the accuracy evaluation you also need the Common Voice sentences in `third_party/common-voice/server/data/zh-TW`. Then run `uv run python -m zhime.evaluate --split test`.

There is also an optional Qwen3-0.6B reranker: run `uv sync --extra rerank`, then set the environment variable `ZHIME_RERANK=1`. It is slower and no more accurate than the default model, so it is off by default.

## License

zhime's code is MIT-licensed. Third-party code and data (PIME, McBopomofo, wordfreq, the PTT dataset, Wikipedia) keep their own licenses; see [NOTICE.txt](NOTICE.txt).
