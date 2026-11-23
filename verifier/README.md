# Bağımsız verifier

src/independent_verifier kaynak testi yürütücüsünü ve bağımsız doğrulama pipeline kaynaklarını içerir. public-fixtures mevcut kaynak testi örnekleridir; gizli runtime oracle değildir. Ayrı klasör/aynı-UID subprocess gerçek izolasyon sağlamaz. Backend verification istemcileri product/backend/company_os/verification içinde kalır. Runtime enrolled verifier yokken reddedilir; kabulü Kernel kaydeder.
