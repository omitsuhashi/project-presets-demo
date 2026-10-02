# Changelog

## 1.0.0

- Node.js、Hono、Next.js、Python スクリプトの構成 Profile。
- フレームワーク・依存の固定版と、対応する lint / TypeScript 設定を一括管理。
- 依存差分の preview・適用・整合チェック、案件側の変更保護。
- Hono / Next.js の検証、依存と設定の更新・復旧を実証するデモ。

## 1.1.0

- GitHub Release から npm tarball と Python wheel / sdist を配布。npm・PyPI アカウント不要。
- TypeScript CLI に `--sync` を追加し、Profile 依存・npm lock・配布版の整合性を検査。
- Python wheel に Ruff の exact version と設定を同梱。案件の上書きを保持する導入・更新・検査 CLI を追加。
- 両言語の更新 script と、同じ major の Release から更新 PR を作る reusable workflow を追加。
- 実際の tarball / wheel の更新、手動変更の拒否、設定保持、lock と設定の revert を CI で検証。

既存 Git 配布の TypeScript import と Python 設定パスは保持。Python の wheel 方式へは、旧 submodule の取り外しと設定参照の変更をレビューして移行する。フレームワーク切替と業務コード移行は引き続き手動。
