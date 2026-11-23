# Worker girişleri

Bu alan ayrı yürütme girişleri içindir. Mevcut scheduler/claim/dispatch uygulaması backend içindedir; bu geçiş yeni worker servisi kurmadı. Gerektiğinde görev, outbox ve reconciliation girişleri eklenir; iş kuralları burada çoğaltılmaz.
