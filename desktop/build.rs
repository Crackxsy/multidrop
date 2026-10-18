use std::{env, fs, path::{Path, PathBuf}};

// Embeds the web app into the binary. The app is pages/, the same files GitHub Pages
// serves: index.html, app.js, wire.js, style.css and wireweave's src/. The submodule's
// tests, node_modules and metadata are not part of the app and are left out.
fn main() {
    let manifest = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let pages = manifest.join("..").join("pages");
    println!("cargo:rerun-if-changed={}", pages.display());

    let mut files: Vec<String> = ["index.html", "app.js", "wire.js", "style.css"]
        .iter()
        .map(|s| s.to_string())
        .collect();
    let src = pages.join("vendor").join("wireweave").join("src");
    let mut modules: Vec<String> = fs::read_dir(&src)
        .unwrap_or_else(|e| panic!("wireweave is not checked out ({}): {e}", src.display()))
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .filter(|name| name.ends_with(".js"))
        .map(|name| format!("vendor/wireweave/src/{name}"))
        .collect();
    files.append(&mut modules);
    files.sort();

    let mut out = String::from("pub static FILES: &[(&str, &[u8])] = &[\n");
    for rel in &files {
        let abs = pages.join(rel);
        assert!(abs.is_file(), "missing app file {}", abs.display());
        out += &format!("    ({:?}, include_bytes!({:?})),\n", rel, abs.display().to_string());
    }
    out += "];\n";
    let dest = Path::new(&env::var("OUT_DIR").unwrap()).join("assets.rs");
    fs::write(dest, out).unwrap();
}
