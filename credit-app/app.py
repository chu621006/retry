import streamlit as st
import pandas as pd
import io
import tabula # 或 import camelot, 如果您選擇使用 camelot-py

# --- 1. GPA 轉換函數 ---
def parse_gpa_to_numeric(gpa_str):
    """
    Converts GPA string to a numeric value for comparison.
    This mapping can be adjusted based on specific grading scales.
    For this example, we define C- and above as passing.
    """
    gpa_map = {
        'A+': 4.3, 'A': 4.0, 'A-': 3.7,
        'B+': 3.3, 'B': 3.0, 'B-': 2.7,
        'C+': 2.3, 'C': 2.0, 'C-': 1.7,
        'D+': 1.3, 'D': 1.0, 'D-': 0.7,
        'E': 0.0, 'F': 0.0,
        '抵免': 999.0, # Assign a very high value for '抵免' to ensure it passes
        '通過': 999.0  # Assign a very high value for '通過' to ensure it passes
    }
    return gpa_map.get(gpa_str.strip(), 0.0) # Default to 0.0 for unknown or failing grades

# --- 2. 成績分析函數 ---
def analyze_student_grades(df):
    """
    Analyzes a DataFrame of student grades to calculate total earned credits
    and remaining credits for graduation.

    Args:
        df (pd.DataFrame): DataFrame containing '學分' (credits) and 'GPA' columns.

    Returns:
        tuple: (total_earned_credits, remaining_credits_to_graduate, passed_courses_df)
    """
    GRADUATION_REQUIREMENT = 128

    # Ensure '學分' is numeric, coercing errors to NaN then filling with 0
    df['學分'] = pd.to_numeric(df['學分'], errors='coerce').fillna(0)

    # Convert GPA to numeric representation for comparison
    df['GPA_Numeric'] = df['GPA'].apply(parse_gpa_to_numeric)

    # Determine if a course passed (C- equivalent or higher, or '抵免', or '通過')
    # C- corresponds to a numeric value of 1.7 in our mapping
    df['是否通過'] = df['GPA_Numeric'].apply(lambda x: x >= 1.7)

    # Filter for passed courses, handle the '勞作成績為:未通過' row which might appear
    passed_courses_df = df[df['是否通過'] & (df['學分'] > 0)].copy() # Only count courses with > 0 credit

    # Calculate total earned credits
    total_earned_credits = passed_courses_df['學分'].sum()

    # Calculate remaining credits
    remaining_credits_to_graduate = max(0, GRADUATION_REQUIREMENT - total_earned_credits)

    return total_earned_credits, remaining_credits_to_graduate, passed_courses_df

# --- Streamlit 應用程式主體 ---
def main():
    st.title("總學分查詢系統 🎓")
    st.write("請上傳您的成績總表 PDF 檔案，系統將會為您查詢目前總學分與距離畢業所需的學分。")
    st.info("💡 確保您的成績單 PDF 是清晰的表格格式，以獲得最佳解析效果。")

    uploaded_file = st.file_uploader("上傳成績總表 PDF 檔案", type=["pdf"])

    if uploaded_file is not None:
        st.success("檔案上傳成功！正在分析中...")

        try:
            # 使用 tabula-py 提取 PDF 中的表格
            # pages='all' 表示提取所有頁面
            # lattice=True 或 stream=True 根據 PDF 表格類型選擇，通常 lattice 適合有明確線條的表格
            # 根據您的 PDF 範例，表格結構清晰，試試看 lattice 模式
            # 您提供的 PDF 中，科目名稱可能有多行，tabula-py 可能會將它們合併，這需要進一步確認效果
            # 這裡需要指定 column names，因為 tabula-py 可能不會自動識別正確的 header
            # 由於你的PDF沒有提供明確的header，可能需要手動定義columns並從row 0開始
            raw_dfs = tabula.read_pdf(
                io.BytesIO(uploaded_file.getvalue()),
                pages='all',
                multiple_tables=True,
                lattice=True, # 嘗試使用 lattice 模式，因為表格線條較明顯
                area = [90, 0, 800, 600], # 根據PDF內容大致劃定表格區域 [top, left, bottom, right] (in points)
                # columns = [50, 100, 150, 300, 350, 400], # 如果表格有不規則的列，可以嘗試手動指定列的位置
                pandas_options={'header': None} # 不將第一行識別為header，因為第一行可能是數據
            )

            if not raw_dfs:
                st.warning("未能從 PDF 中提取任何表格。請檢查 PDF 格式或嘗試調整解析參數。")
                return

            # 合併所有提取到的 DataFrame
            full_grades_df = pd.DataFrame()
            expected_columns = ["學年度", "學期", "選課代號", "科目名稱", "學分", "GPA"]

            for df_table in raw_dfs:
                # 簡單的清理：去除可能不是成績數據的行（例如體育門檻、版權資訊等）
                # 確保 DataFrame 至少有6列（對應我們的資料）
                if df_table.shape[1] >= len(expected_columns):
                    # 重新命名列，確保一致性
                    df_table.columns = expected_columns[:df_table.shape[1]]

                    # 過濾掉那些明顯不是成績行的資料，例如開頭不是數字的學年度
                    # 並且排除"勞作成績為:未通過"這樣的總結行
                    df_table = df_table[
                        df_table['學年度'].astype(str).str.match(r'^\d{3}$') &
                        ~df_table['學年度'].astype(str).str.contains('勞作成績')
                    ]
                    full_grades_df = pd.concat([full_grades_df, df_table], ignore_index=True)
                else:
                    st.warning(f"跳過一個格式不符的表格: {df_table.head()}")

            # 清理最終的 DataFrame
            # 移除所有列都是 NaN 的行 (可能來自解析錯誤)
            full_grades_df.dropna(how='all', inplace=True)
            # 移除可能由於PDF解析造成的空白字元
            for col in full_grades_df.columns:
                full_grades_df[col] = full_grades_df[col].astype(str).str.strip()

            if not full_grades_df.empty:
                # 執行學分分析
                total_credits, remaining_credits, passed_courses_df = analyze_student_grades(full_grades_df)

                st.subheader("查詢結果 ✅")
                st.metric("目前總學分", total_credits)
                st.metric("距離畢業所需學分 (共128學分)", remaining_credits)

                st.subheader("通過的課程列表 📖")
                st.dataframe(passed_courses_df[['學年度', '學期', '科目名稱', '學分', 'GPA']])

                with st.expander("查看原始提取的數據 (用於除錯)"):
                    st.dataframe(full_grades_df)
            else:
                st.warning("未能從 PDF 中提取有效的成績數據。請檢查 PDF 格式或嘗試調整解析參數。")

        except Exception as e:
            st.error(f"處理 PDF 檔案時發生錯誤：{e}")
            st.info("請確認您已正確安裝 `tabula-py` 並配置 Java 環境。若問題持續，可能是 PDF 格式較為複雜，需要調整 `tabula.read_pdf` 的參數。")
            st.exception(e) # 顯示更詳細的錯誤信息

if __name__ == "__main__":
    main()