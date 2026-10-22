use plume_core::AnisetteConfiguration;
use plume_core::auth::anisette_data::AnisetteData;

fn main() -> anyhow::Result<()> {
    let _ = rustls::crypto::ring::default_provider().install_default();
    let path = std::env::args().nth(1).ok_or_else(|| anyhow::anyhow!("isolated configuration path required"))?;
    std::fs::create_dir_all(&path)?;
    tokio::runtime::Builder::new_current_thread().enable_all().build()?.block_on(async {
        let config = AnisetteConfiguration::default().set_configuration_path(path.into());
        let data = AnisetteData::new(config).await?;
        for key in ["X-Apple-I-MD", "X-Apple-I-MD-M"] {
            anyhow::ensure!(data.base_headers.get(key).is_some_and(|value| !value.is_empty()), "Anisette field missing: {}", key);
        }
        println!("Upstream-supported Anisette produced both required authentication fields; values withheld.");
        Ok(())
    })
}
