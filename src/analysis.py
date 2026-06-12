from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder
from sklearn.cluster import KMeans
from sklearn.preprocessing import LabelEncoder


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


def load_data() -> pd.DataFrame:
    xlsx_path = DATA_DIR / "characters.xlsx"
    csv_path = DATA_DIR / "characters.csv"
    sample_path = DATA_DIR / "characters_sample.csv"

    if xlsx_path.exists():
        df = pd.read_excel(xlsx_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    elif sample_path.exists():
        df = pd.read_csv(sample_path)
    else:
        raise FileNotFoundError("请先在 data/ 中放入 characters.xlsx、characters.csv 或 characters_sample.csv")

    rename_map = {
        "hair": "发色",
        "eye": "瞳色",
        "chara": "萌点",
        "特点": "萌点",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    required = ["发色", "瞳色", "萌点"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"数据缺少必要字段: {', '.join(missing)}")

    df = df.dropna(subset=required).copy()
    for column in required:
        df[column] = df[column].astype(str).str.strip()
    return df


def split_traits(value: str) -> list[str]:
    value = value.replace("，", ",").replace("、", ",").replace("/", ",")
    return [item.strip() for item in value.split(",") if item.strip()]


def run_kmeans(df: pd.DataFrame, clusters: int = 4) -> pd.DataFrame:
    result = df.copy()
    hair_encoder = LabelEncoder()
    eye_encoder = LabelEncoder()
    result["发色编码"] = hair_encoder.fit_transform(result["发色"])
    result["瞳色编码"] = eye_encoder.fit_transform(result["瞳色"])

    features = result[["发色编码", "瞳色编码"]]
    model = KMeans(n_clusters=min(clusters, len(result)), random_state=42, n_init=10)
    result["聚类结果"] = model.fit_predict(features)
    return result


def run_apriori(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    transactions = []
    for _, row in df.iterrows():
        items = [f"发色_{row['发色']}", f"瞳色_{row['瞳色']}"]
        items.extend(f"萌点_{trait}" for trait in split_traits(row["萌点"]))
        transactions.append(items)

    encoder = TransactionEncoder()
    encoded = encoder.fit(transactions).transform(transactions)
    one_hot = pd.DataFrame(encoded, columns=encoder.columns_)

    frequent = apriori(one_hot, min_support=0.05, use_colnames=True)
    if frequent.empty:
        return frequent, pd.DataFrame()

    rules = association_rules(frequent, metric="confidence", min_threshold=0.3)
    if rules.empty:
        return frequent, rules

    mask = rules.apply(
        lambda row: any(item.startswith(("发色_", "瞳色_")) for item in row["antecedents"])
        and any(item.startswith("萌点_") for item in row["consequents"]),
        axis=1,
    )
    return frequent, rules[mask].sort_values("lift", ascending=False)


def save_charts(df: pd.DataFrame, rules: pd.DataFrame) -> None:
    hair_counts = df["发色"].value_counts()
    ax = hair_counts.plot(kind="bar", title="发色分布", figsize=(8, 5))
    ax.set_xlabel("发色")
    ax.set_ylabel("数量")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "hair_distribution.png", dpi=160)
    plt.close()

    eye_counts = df["瞳色"].value_counts()
    ax = eye_counts.plot(kind="bar", title="瞳色分布", figsize=(8, 5))
    ax.set_xlabel("瞳色")
    ax.set_ylabel("数量")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "eye_distribution.png", dpi=160)
    plt.close()

    if not rules.empty:
        plt.figure(figsize=(8, 5))
        plt.scatter(
            rules["support"],
            rules["confidence"],
            s=rules["lift"] * 60,
            alpha=0.65,
        )
        plt.xlabel("Support")
        plt.ylabel("Confidence")
        plt.title("关联规则分布")
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "association_rules.png", dpi=160)
        plt.close()


def main() -> None:
    df = load_data()
    clustered = run_kmeans(df)
    frequent, rules = run_apriori(clustered)

    clustered.to_csv(OUTPUT_DIR / "clustered_characters.csv", index=False, encoding="utf-8-sig")
    frequent.to_csv(OUTPUT_DIR / "frequent_itemsets.csv", index=False, encoding="utf-8-sig")
    rules.to_csv(OUTPUT_DIR / "association_rules.csv", index=False, encoding="utf-8-sig")
    save_charts(clustered, rules)

    print("分析完成，结果已输出到 outputs/ 目录。")


if __name__ == "__main__":
    main()
