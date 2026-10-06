# yue-voice

以 OmniVoice 合成一段粵語，再以 SenseVoiceSmall 轉寫校對的本機工具。它不是段落切分器：每次只接收一段，限制為最多 **180 個中文字等價單位**，超出會清楚報錯。

## 行為保證

- 合成語言固定為 `yue`。
- 支援互斥的自動音色、聲音克隆與聲音設計模式。
- 每次候選都由 SenseVoiceSmall 以 `yue` 轉寫，使用 **T2S-normalized CER** 比較。
- 正規化會做 Unicode NFKC、大小寫一致化，並忽略空白、標點與 emoji 元件；原文會以 OpenCC `t2s` 轉成簡體後比較。ASR 轉寫則維持其輸出的漢字形式。
- 只有 CER **嚴格小於 5%** 的候選才是 `accepted: true`。同音字仍算差異。
- 最多嘗試 10 次。全部不達標時會輸出 CER 最低的 best-effort WAV，但標記 `accepted: false`；CLI 預設以非零狀態結束。
- 每次嘗試會改變 Python／Torch 隨機 seed，並比對 WAV SHA-256；若生成出重複音訊，會記錄原因並停止，不會假裝重試十次。

## 安裝

需求：macOS（Apple Silicon 最佳）、[uv](https://docs.astral.sh/uv/)，以及首次執行時可下載模型的網絡。

```sh
cd /Users/user/Documents/workspace/yue-voice
uv python install 3.13
uv sync
```

專案固定在 Python 3.13，依賴版本由 `uv.lock` 鎖定。`uv` 建立的 `.venv/` 是可刪除重建的套件環境；它不是模型快取。

## 使用

### 自動音色

```sh
uv run yue-voice generate \
  --text "今日天氣幾好，我哋出去行個圈先。" \
  --artifact-dir artifacts
```

### 聲音克隆

把私人的參考音檔及其**逐字稿**放在 `references/`（該資料夾內容不會提交到 Git），或使用任何本機絕對／相對路徑。為免 OmniVoice 暗中下載另一個 Whisper 模型，clone mode 強制要求逐字稿。

```sh
uv run yue-voice generate \
  --mode clone \
  --text "多謝你今日幫手，辛苦晒。" \
  --ref-audio references/speaker.wav \
  --ref-text-file references/speaker.txt
```

### 聲音設計

```sh
uv run yue-voice generate \
  --mode design \
  --instruct "female, calm, warm" \
  --text "聽日朝早九點半開始直播。"
```

`--device mps`、`--device cpu` 或 `--device cuda:0` 可明確覆寫裝置。未指定時，工具優先使用 MPS；MPS 無法載入某個模型時才個別回退 CPU。CUDA 只會在明確指定時使用。

每次執行建立 `artifacts/<run-id>/`：

- `output.wav`：通過校對的候選，或未達標時的最低 CER best-effort。
- `result.json`：原文、T2S-normalized 文本、每次 seed、轉寫、CER、音訊雜湊、耗時與最終狀態。
- `candidates/`：只有加上 `--keep-candidates` 才保留的所有候選 WAV。

如確實需要 best-effort 也視為流程成功，加上 `--allow-best-effort`；否則 `accepted: false` 會回傳 exit code 2。

## Benchmark

版本控制的 `benchmarks/cantonese.jsonl` 有 24 段粵語測例，當中包含由可提交的 `sample.txt` 以空行拆出的三個非空段落。執行：

```sh
uv run yue-voice benchmark --corpus benchmarks/cantonese.jsonl --artifact-dir artifacts
```

亦可直接以自己的多段文字測評；空段會略過：

```sh
uv run yue-voice benchmark --text-file sample.txt --artifact-dir artifacts
```

每個 case 的「單純生成」是閉環中的第 1 個候選；「校驗生成」從**同一個第 1 次候選**起步，最多再產生九次。報告因此比較的是相同起點，而不是兩組不同隨機實驗。報告會寫入 `artifacts/benchmark-<run-id>/report.json` 與 `report.md`，並包含平均 CER、<5% 達標率、平均嘗試次數、平均耗時與逐項結果。

## 實測結果

以下是已在本機完成的真實 baseline vs 閉環測評，不是上游模型宣稱的 benchmark：

- 執行時間：2026-10-06；Python 3.13.12；依賴由此 repo 的 `uv.lock` 鎖定。
- 模型：`k2-fsa/OmniVoice`、`iic/SenseVoiceSmall`；TTS 與 ASR 都實際使用 `mps`。
- 指令：`uv run yue-voice benchmark --corpus benchmarks/cantonese.jsonl --seed 20261006 --artifact-dir artifacts`。
- 語料：24 段；每段最多 10 次；總耗時 406.99 秒（約 6 分 47 秒）。
- 原始、逐 case 結果位於 Git ignore 的 `artifacts/benchmark-20261006T091334300930Z/report.json` 與 `report.md`。

| Metric | 單純生成（第 1 候選） | 校驗生成（最多 10 次） |
| --- | ---: | ---: |
| 平均 T2S-normalized CER | 6.82% | **4.28%** |
| 相對 CER 改善 | — | **37.33%** |
| `< 5%` 達標率 | 14/24（58.33%） | 17/24（70.83%） |
| 平均嘗試次數 | 1.00 | 4.04 |
| 平均每段時間 | — | 16.96 秒 |

在相同的 24 段、相同的第 1 候選起點下，閉環把平均 CER 降低 2.55 個百分點，並多讓 3 段達到門檻。7 段仍未達標時，輸出會保留為明確標示 `accepted: false` 的 best-effort，不會被偽稱為已校驗成功。

此輪也將三個英文／數字形式的基準項目改成目標粵語讀法（`8%` → `八 percent`、`6pm` → `6 p m`、`HK$1,280` → `一千二百八`），並和 T2S／emoji 正規化一併提交。因此這組結果是當前已提交語料的基準，不能直接和舊版嚴格字形 CER 的 31.86%／29.00% 相比來歸因。

## 模型、快取與清理

| 用途 | 模型 ID／來源 | 預設快取目錄 |
| --- | --- | --- |
| 粵語語音合成 | [`k2-fsa/OmniVoice`](https://huggingface.co/k2-fsa/OmniVoice)／Hugging Face | `~/.cache/yue-voice/models/huggingface/` |
| 粵語 ASR 校對 | [`iic/SenseVoiceSmall`](https://www.modelscope.cn/models/iic/SenseVoiceSmall)／ModelScope + FunASR | `~/.cache/yue-voice/models/modelscope/` |

OpenCC `t2s` 是鎖定在 `.venv/` 的文字正規化套件，並非下載模型。可用 `--model-cache-dir /path/to/cache` 將上述兩個模型子快取移到另一個根目錄。首次 `generate` 或 `benchmark` 才下載權重；模型從不寫入 Git 專案。

查看模型快取大小：

```sh
du -sh ~/.cache/yue-voice/models/*
```

清理時按需求選擇：

```sh
# 只刪除可重新生成的音訊與報告
rm -rf artifacts

# 只刪除私人的本地參考音檔和逐字稿
rm -rf references/*

# 刪除所有下載的模型；下次推論會重新下載
rm -rf ~/.cache/yue-voice/models

# 刪除可由 uv 重建的虛擬環境
rm -rf .venv
```

OmniVoice 與 SenseVoice 的能力、安裝和模型來源以各自官方文件為準：[OmniVoice](https://github.com/k2-fsa/OmniVoice/) · [SenseVoice](https://github.com/QwenAudio/SenseVoice/)。
