# coding=utf-8
import os
import sys
import re
import shutil
import csv
import configparser
import argparse

VERSION=0.2

# 設定ファイルから情報を取得するクラス
class SyncKakeiboConfig:

    def __init__(self):

        configPath = os.path.dirname(__file__) + r"\kakeibo.ini"

        config = configparser.ConfigParser();
        config.read(configPath, encoding='utf-8')

        self.mChangeLogMemoFilePath = config["SETTING"]["CHANGELOGMEMOFILEPATH"]
        self.mKakeiboDir = config["SETTING"]["KAKEIBODIR"]
        self.mName = config["SETTING"]["NAME"]
        self.mMailAddress = config["SETTING"]["MAILADDRESS"]

    # ChangeLogメモのディレクトリ
    def getChangeLogMemoDir(self):
        return os.path.dirname(self.mChangeLogMemoFilePath)

    # ChangeLogメモファイルパス
    def getChangeLogMemoFilePath(self):
        return self.mChangeLogMemoFilePath

    # 家計簿データ置き場ディレクトリ
    def getKakeiboDir(self):
        return self.mKakeiboDir

    # cashbook.csvのパス取得
    def getCashBookFilePath(self):
        return self.getKakeiboDir() + '/cashbook.csv'

    def getCashBookAllFilePath(self):
        return self.getKakeiboDir() + '/cashbook_all.csv'

    def getMailAddress(self):
        return self.mMailAddress

    def getName(self):
        return self.mName

# 費目
class ExpenseItem:

    # ChangeLogメモ上の費目と、かけーぼ上の費目の対応表
    # (ChangeLogメモの費目からかけーぼの費目に変換するために使う)
    himokuConvertMap = {
        '食':'食費',
        '保':'保険',
        '貯':'貯蓄',
        '本':'書籍',
        '酒':'酒代',
        '外':'外食',
        '住':'住宅',
        '活':'生活費',
        '雑':'嗜好品',
        '交':'交通費',
        '娯':'趣味・娯楽費',
        '服':'衣服',
        '通':'通信費',
        '光':'光熱費',
        '医':'医療費',
        '育':'教育費',
        '車':'車維持費',
        '際':'交際費',
        '他':'その他'
    }

    # ChangeLogメモ上の費目からIDを得るためのmap
    himokuCLMemoToIDMap = {}
    # IDからChangeLogメモ上の費目名称を得るためのmap
    idToHimokuCLMap = {}

    # 家計簿アプリ上の費目からIDを得るためのmap
    himokuCBToIDMap = {}
    # IDから家計簿アプリ上の費目名称を得るためのmap
    idToHimokuCBMap = {}

    # 初期化
    @classmethod
    def initTable(cls):
        for index,clMemoHimoku in enumerate(cls.himokuConvertMap):

            kakeiboHimoku = cls.himokuConvertMap[clMemoHimoku]

            cls.himokuCLMemoToIDMap[clMemoHimoku] = index
            cls.idToHimokuCLMap[index] = clMemoHimoku

            cls.himokuCBToIDMap[kakeiboHimoku] = index
            cls.idToHimokuCBMap[index] = kakeiboHimoku

    # ChangeLoeメモ上の費目名から費目IDを得る
    @classmethod
    def getIdFromCLMemoName(cls, name):

        # 初回呼び出し時にインデックス生成
        if len(cls.himokuCLMemoToIDMap) == 0:
            cls.initTable()

        if name in cls.himokuCLMemoToIDMap:
            return cls.himokuCLMemoToIDMap[name]
        else:
            return -1

    # 家計簿アプリ上の費目名から費目IDを得る
    @classmethod
    def getIdFromKakeiboName(cls, name):

        # 初回呼び出し時にインデックス生成
        if len(cls.himokuCBToIDMap) == 0:
            cls.initTable()

        if name in cls.himokuCBToIDMap:
            return cls.himokuCBToIDMap[name]
        else:
            return -1

    # 費目IDからChangeLogメモ上の費目名を得る
    @classmethod
    def getCLMemoName(cls, himokuId):
        if himokuId in cls.idToHimokuCLMap:
            return cls.idToHimokuCLMap[himokuId]
        else:
            return ""

    # 費目IDから家計簿アプリ上の費目名を得る
    @classmethod
    def getKakeiboName(cls, himokuId):
        if himokuId in cls.idToHimokuCBMap:
            return cls.idToHimokuCBMap[himokuId]
        else:
            return ""

class CashItem:

    def __init__(self, date, himokuId, amount, brief):
        self.mDate = date
        self.mHimokuId = himokuId
        self.mAmount = amount
        self.mBrief = brief

    # 費目を取得
    def getHimokuId(self):
        return self.mHimokuId

    def getHimokuCLMemoName(self):
        return ExpenseItem.getCLMemoName(self.mHimokuId)

    def getHimokuKakeiboName(self):
        return ExpenseItem.getKakeiboName(self.mHimokuId)

    # 日付を取得
    def getDate(self):
        return self.mDate

    # 金額を取得(正の値:支出  負の値:収入)
    def getAmount(self):
        return self.mAmount

    # 収入の場合に収入金額を正の値で返す(支出の場合0を返す)
    def getIncomeAmount(self):
        return -self.mAmount if self.mAmount < 0 else 0

    # 支出の場合に支出金額を正の値で返す(収入の場合0を返す)
    def getSpendingAmount(self):
        return self.mAmount if self.mAmount >= 0 else 0

    #
    def getBalanceCategory(self):
        return "支出" if self.mAmount >= 0 else "収入"

    # メモを取得
    def getBrief(self):
        return self.mBrief

    # 同一かどうかを表す文字列を取得
    def getHash(self):
        return f"{self.mDate}{self.mHimokuId}{self.mBrief}{self.mAmount}"

class CashBook:

    def __init__(self):
        self.items = []

    # cashbook.csvをよむ
    # 読んだ結果、self.itemsにデータ行の配列を保持する
    #
    # @param filePath  cashbook.csvのファイルパス
    # @return 処理の成否を表すBoolean
    def load(self, filePath):

        with open(filePath, "r", encoding='utf-8') as f:

            expected_header = [ "No","日付","収入","支出","費目名","収支区分","メモ","帳簿コード","支払コード","請求日&支払回数","請求No","送金元orチャージ" ]

            reader = csv.reader(f)
        
            for index,columns in enumerate(reader):

                if index == 0:
                    # 1行目の場合はヘッダ名の確認
                    if len(columns) != 12:
                        print(f"Error: 意図しないヘッダ構成(12列でない)")
                        return False

                    for expect, actual in zip(expected_header, columns):
                        if expect != actual:
                            print(f"Error: 意図しないヘッダ構成 expect:{expect} actual:{actual}")
                            return False
                else:
                    # 2行目以降を読む(1行目はヘッダのため読み飛ばす)
                    date = columns[1]
                    himokuId = ExpenseItem.getIdFromKakeiboName(columns[4])
                    if himokuId == -1:
                        print(f'Warning: Line.{index+1} [家計簿アプリ側]不明な費目のため無視します {columns[4]}')
                        continue

                    if columns[5] == '支出':
                        amount = int(columns[3])
                    else:
                        amount = -(int(columns[2]))

                    brief = columns[6]

                    self.items.append(CashItem(date, himokuId, amount, brief))

        return True

    @classmethod
    def saveAllItems(cls, items, filePath):

        # 元のファイルを.bakに退避
        filePathBak = filePath + ".bak"
        shutil.copyfile(filePath, filePathBak)

        with open(filePath, "w", encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=",", quotechar='"', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["No", "日付","収入","支出",
                             "費目名","収支区分","メモ","帳簿コード","支払コード","請求日&支払回数","請求No","送金元orチャージ"])
            for index,item in enumerate(items):

                himokuName = item.getHimokuKakeiboName()

                columns = [ str(index+1), item.getDate(), item.getIncomeAmount(), item.getSpendingAmount(),
                            himokuName, item.getBalanceCategory(), item.getBrief(),"0","0","","","" ]
                writer.writerow(columns)

    @classmethod
    def saveItems(cls, items, filePath):

        # 元のファイルを.bakに退避
        filePathBak = filePath + ".bak"
        shutil.copyfile(filePath, filePathBak)

        count = len(items)
        with open(filePath, "w", encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=",", quotechar='"', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["No","日付","収入","支出","費目名","収支区分","メモ","帳簿コード","支払コード","請求日&支払回数","請求No","送金元orチャージ"])
            writer.writerow(["9999999","99991231","0","0",f"件数={count}  count={count}","支出","メモ","0","0","","",""])

    def getItems(self):
        return self.items

class ChangeLogMemo:

    config = None

    def __init__(self):

        self.items = []

    # ChangeLogメモから買い物ログを抽出する
    # @param filePath ChangeLogメモファイル
    def loadBuyLog(self, filePath):

        date = ""
        inBuyLog = False

        with open(filePath, "r", encoding='utf-8') as f:
        
            for index,line in enumerate(f):

                line = line.rstrip()

                # 日付行なら日付を取得してスキップ
                if re.match(r'^\d\d\d\d', line):
                  date = re.sub(r'^(\d\d\d\d)-(\d\d)-(\d\d).+$', r'\1\2\3', line)
                  inBuyLog = False
                  continue

                # 買い物ログ行の検出
                if re.match(r'^\t *\* *買い物ログ.+$', line):
                  inBuyLog = True
                  continue

                if inBuyLog == False:
                  continue

                if re.match(r'^\t\*', line):
                  # 買い物ログと同一日付の、後方にあるエントリの検出
                  inBuyLog = False
                  continue

                if re.match(r'^$', line):
                  # 空行はスキップ
                  continue

                # 以下、買い物ログ内におけるログ処理

                # 費目/品名/金額を抽出
                line = line.strip("\t ")
                cols = line.split(" ")
                if len(cols) != 3:
                  print("Warning: Line{index+1}: 買い物ログとして想定しない形式のため無視します -- {line}")
                  continue

                himokuId = ExpenseItem.getIdFromCLMemoName(cols[0])
                remarks = cols[1]
                amount = int(cols[2])

                if himokuId == -1:
                  print(f"Warning: Line.{index+1}: [買い物ログ側]不明な費目のため無視します -- {cols[0]}")
                  continue

                if remarks == "(記載なし)":
                  remarks = ""

                self.items.append(CashItem(date, himokuId, amount, remarks))
        return True

    def getItems(self):
        return self.items

    @classmethod
    def applyBuyLog(cls, buyLog, filePath):

        # 元のファイルを.bakに退避
        filePathBak = filePath + ".bak"
        shutil.copyfile(filePath, filePathBak)

        # 一時出力用のメモ
        fileOut = open(filePath, "w", encoding='utf-8')

        date = ''
        dateEnd = "99991231"

        outputDateMap = set()

        # ChangeLog.txtをよむ
        with open(filePathBak, "r", encoding='utf-8') as f:
        
            inBuyLog = False
            for index,rawline in enumerate(f):

                line = rawline.rstrip()
        
                # 日付行なら日付を取得してスキップ
                if re.match(r'^\d\d\d\d', line):

                    if date != '' and (not date in outputDateMap):
                        # 別の日付に移ったとき、前行の日付の買い物ログが存在しなかった場合は新規に生成する
                        cls.writeBuyLogEntry(fileOut, buyLog, date)
                        outputDateMap.add(date)

                    # 次の日付に変更
                    date = re.sub(r'^(\d\d\d\d)-(\d\d)-(\d\d).+$', r'\1\2\3', line)

                    # 当日と前回出力した日付の間に空白の期間がある場合はそれを補完する
                    cls.writeBuyLog(fileOut, buyLog, date, dateEnd, outputDateMap)
                    dateEnd = date

                    # 当日の行を出力する
                    fileOut.write(line + "\n")

                    inBuyLog = False
                    continue

                # 買い物ログかどうか
                if re.match(r'^\t *\* *買い物ログ *', line):
                    # 該当する日付の買い物ログを出力
                    if not date in outputDateMap:
                        cls.writeBuyLogEntry(fileOut, buyLog, date)
                        outputDateMap.add(date)
                    inBuyLog = True
                    continue
  
                # 別のエントリ
                if re.match(r'\t\*', line):
                    inBuyLog = False

                if inBuyLog == False:
                    fileOut.write(rawline)

        fileOut.close()

    @classmethod
    def getConfig(cls):

        if cls.config == None:
            cls.config = SyncKakeiboConfig()

        return cls.config

    @classmethod
    def writeBuyLogEntry(cls, fileOut, buyLog, date):

        # 当日の買い物ログデータを取得する
        items = buyLog.getLogAt(date)

        if len(items) == 0:
            return

        warningItems = []

        # ヘッダ行を出力
        fileOut.write('\t* 買い物ログ:\n')

        # ファイルに出力する
        for item in items:

            himoku = item.getHimokuCLMemoName()
            if himoku == '':
                warningItems.append(item)
                himoku = "他"

            amount = item.getAmount()
            remarks = item.getBrief()
            if remarks == "":
                remarks = "(記載なし)"

            fileOut.write(f'\t{himoku} {remarks} {amount}\n')

        fileOut.write("\n")

    @classmethod
    def writeBuyLog(cls, fileOut, buyLog, dateStart, dateEnd, outputDateMap):

        config = cls.getConfig()

        NAME = config.getName()
        MAILADDRESS = config.getMailAddress()

        warningItems = []

        # 指定した期間(dateStart-dateEnd)のうち、買い物ログデータが存在する日付のリストを取得
        # (dateStart,dateEnd自身は含まない)
        dates = buyLog.getDateRange(dateStart, dateEnd)
        for date in reversed(dates):

            if date in outputDateMap:
                # 出力済みの日付
                continue

            # 日付を出力
            datestr = re.sub(r'(\d\d\d\d)(\d\d)(\d\d)', r'\1-\2-\3', date)
            fileOut.write(f'{datestr} {NAME} <{MAILADDRESS}>\n')
            fileOut.write('\n')
  
            # 該当する日付の買い物ログを出力
            cls.writeBuyLogEntry(fileOut, buyLog, date)
            outputDateMap.add(date)


# 買い物ログデータを扱うクラス
class BuyLog:

    def __init__(self):

        # 同一アイテムの有無を判定するためのセット
        self.keys = set()

        # 全期間のアイテム
        self.mergedItems = []

        # 日付別のアイテムリスト
        self.itemsPerDate = {}

    # 追加
    def append(self, items):

        for item in items:

          # 同一アイテム判定
          # 日付/費目/名前/額が同じものは同一アイテムとみなし、追加しない
          keystr = item.getHash()
          if keystr in self.keys:
            continue

          self.mergedItems.append(item)

          date = item.getDate()
          if date in self.itemsPerDate:
            self.itemsPerDate[date].append(item)
          else:
            self.itemsPerDate[date] = [ item ]

          self.keys.add(keystr)

    # 指定した日付の買い物のリストを取得する
    def getLogAt(self, date):

      if date in self.itemsPerDate:
        return self.itemsPerDate[date]
      else:
        return []

    # 指定した範囲(dateStart,dateEnd)の日付のリストを取得
    def getDateRange(self, dateStart, dateEnd):

        result = []

        start = int(dateStart)
        end = int(dateEnd)

        for date in self.itemsPerDate:
            if start < int(date) and int(date) < end:
                result.append(date)

        result.sort()
        return result

    # 全期間のリストを取得
    def getMergedItems(self):
      return self.mergedItems

class Memo:
    def __init__(self, memofile):
        self.items = []

        with open(memofile, "r", encoding='utf-8') as f:

            date = ''
        
            for index,rawline in enumerate(f):

                line = rawline.rstrip()
        
                # 日付行なら日付を取得
                if re.match(r'^\d\d\d\d', line):

                    # 次の日付に変更
                    date = re.sub(r'^(\d\d\d\d)-(\d\d)-(\d\d).*$', r'\1\2\3', line)
                    continue

                # 買い物ログ
                if re.match(r'^\t', line):

                    # 費目/品名/金額を抽出
                    line = line.strip("\t ")
                    cols = line.split(" ")
                    if len(cols) != 3:
                        print("Warning: Line{index+1}: 想定しない形式のため無視します -- {line}")
                        continue

                    himokuId = ExpenseItem.getIdFromCLMemoName(cols[0])
                    remarks = cols[1]
                    amount = int(cols[2])

                    if himokuId == -1:
                        print(f"Warning: Line.{index+1}: [メモファイル側]不明な費目のため無視します -- {cols[0]}")
                        continue

                    self.items.append(CashItem(date, himokuId, amount, remarks))
                    continue


    def getItems(self):
        return self.items

def syncKakeibo(args):
    conf = SyncKakeiboConfig()

    # ChangeLogメモ置き場の有無を確認
    baseDir = conf.getChangeLogMemoDir()
    if os.path.isdir(baseDir) == False:
        print(f"Error: ChangeLogメモフォルダ {baseDir} が存在しません")
        return 1

    # かけーぼ置き場の有無を確認
    kakeiboDir = conf.getKakeiboDir()
    if os.path.isdir(kakeiboDir) == False:
        print(f"Error: かけーぼ同期フォルダ {kakeiboDir} が存在しません")
        return 1

    # かけーぼのCSVを読む
    print("Loading CSV...")
    cashBook = CashBook()
    if cashBook.load(conf.getCashBookAllFilePath()) == False:
        return 1

    # ChangeLogファイルパスを取得
    changeLogMemoFilePath = conf.getChangeLogMemoFilePath()
    print(f"Loading ChangeLogMemo {changeLogMemoFilePath} ...")

    # ChangeLogメモから買い物ログデータを抽出
    buyLogOnMemo = ChangeLogMemo()
    buyLogOnMemo.loadBuyLog(changeLogMemoFilePath)

    # かけーぼのデータとChangeLogメモの買い物データのマージ
    print("Merging...")
    buyLog = BuyLog()
    buyLog.append(cashBook.getItems())
    buyLog.append(buyLogOnMemo.getItems())

    # マージ後の買い物ログをChangeLogメモに適用する
    print("Updateing ChangeLogMemo...")
    ChangeLogMemo.applyBuyLog(buyLog, changeLogMemoFilePath)

    # マージ後の買い物ログをcashbook.csvに書き出す
    ## cashbook.csv
    print("Updateing cashbook.csv...")
    CashBook.saveItems(buyLog.getMergedItems(), conf.getCashBookFilePath())
    ## cashbook_all.csv
    print("Updateing cashbook_all.csv...")
    CashBook.saveAllItems(buyLog.getMergedItems(), conf.getCashBookAllFilePath())

def importMemo(args):

    conf = SyncKakeiboConfig()

    # ChangeLogメモ置き場の有無を確認
    baseDir = conf.getChangeLogMemoDir()
    if os.path.isdir(baseDir) == False:
        print(f"Error: ChangeLogメモフォルダ {baseDir} が存在しません")
        return 1

    # ChangeLogファイルパスを取得
    changeLogMemoFilePath = conf.getChangeLogMemoFilePath()
    print(f"Loading ChangeLogMemo {changeLogMemoFilePath} ...")

    # ChangeLogメモから買い物ログデータを抽出
    buyLogOnMemo = ChangeLogMemo()
    buyLogOnMemo.loadBuyLog(changeLogMemoFilePath)

    # メモファイルから買い物ログデータを抽出
    memofilePath = args.memofile
    print(f"Loading Memo {memofilePath} ...")
    memo = Memo(memofilePath)

    # メモのデータとChangeLogメモの買い物データのマージ
    print("Merging...")
    buyLog = BuyLog()
    buyLog.append(memo.getItems())
    buyLog.append(buyLogOnMemo.getItems())

    # マージ後の買い物ログをChangeLogメモに適用する
    print("Updateing ChangeLogMemo...")
    ChangeLogMemo.applyBuyLog(buyLog, changeLogMemoFilePath)

# 引数に応じて処理を分ける
def main():
    parser = argparse.ArgumentParser(description='個人用ChangeLogメモの買い物ログ回りのユーティリティ')
    subparsers = parser.add_subparsers()
    # syncコマンドの定義
    parser1 = subparsers.add_parser('sync', help='家計簿アプリとの同期を行います')
    parser1.set_defaults(handler=syncKakeibo)

    # importコマンドの定義
    parser2 = subparsers.add_parser('import', help='作業用メモをChangeLogメモの買い物リストとして取り込みます')
    parser2.add_argument('memofile', help='メモファイルのパス')
    parser2.set_defaults(handler=importMemo)

    args = parser.parse_args()
    if hasattr(args, 'handler'):
        args.handler(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass


