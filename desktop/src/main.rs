// MultiDrop, web edition. Serves the browser app embedded in this file on 127.0.0.1
// and opens it. The page does all the work: devices find each other through nostr
// relays and WebRTC, and files stream straight to a folder the user picks.
//
//   multidrop-web            serve on a fixed port and open the browser
//   multidrop-web --no-open  serve only, print the address
//   multidrop-web --selftest check the embedded app is served (used by CI)

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::Command;
use std::thread;

include!(concat!(env!("OUT_DIR"), "/assets.rs"));

// A fixed port keeps the browser's origin, and so the page's saved zone, folder and
// name, the same from one launch to the next.
const PORTS: std::ops::RangeInclusive<u16> = 47823..=47843;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--selftest") {
        std::process::exit(selftest());
    }
    let listener = match bind() {
        Some(l) => l,
        None => {
            eprintln!("MultiDrop: no free port in {}-{}", PORTS.start(), PORTS.end());
            std::process::exit(1);
        }
    };
    let url = format!("http://127.0.0.1:{}/", listener.local_addr().unwrap().port());
    println!("MultiDrop is running at {url}");
    println!("Close this window to stop.");
    if !args.iter().any(|a| a == "--no-open") {
        open(&url);
    }
    for stream in listener.incoming().flatten() {
        thread::spawn(move || serve(stream));
    }
}

fn bind() -> Option<TcpListener> {
    PORTS.clone().find_map(|port| TcpListener::bind(("127.0.0.1", port)).ok())
}

fn serve(mut stream: TcpStream) {
    let mut reader = match stream.try_clone() {
        Ok(clone) => BufReader::new(clone),
        Err(_) => return,
    };
    let mut request = String::new();
    if reader.read_line(&mut request).is_err() {
        return;
    }
    // Drain the headers; the response does not depend on them.
    loop {
        let mut header = String::new();
        match reader.read_line(&mut header) {
            Ok(0) | Err(_) => break,
            Ok(_) if header == "\r\n" || header == "\n" => break,
            Ok(_) => {}
        }
    }
    let mut parts = request.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("/");
    let path = target.split('?').next().unwrap_or("/");
    let name = match path.trim_start_matches('/') {
        "" => "index.html",
        other => other,
    };

    // Only the embedded files exist; nothing is read from disk, so there is no path to escape.
    let (status, content_type, body): (&str, &str, &[u8]) = match (method, FILES.iter().find(|(n, _)| *n == name)) {
        ("GET" | "HEAD", Some((_, bytes))) => ("200 OK", content_type(name), bytes),
        ("GET" | "HEAD", None) => ("404 Not Found", "text/plain; charset=utf-8", b"not found"),
        _ => ("405 Method Not Allowed", "text/plain; charset=utf-8", b"method not allowed"),
    };
    let head = format!(
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n",
        body.len()
    );
    let _ = stream.write_all(head.as_bytes());
    if method != "HEAD" {
        let _ = stream.write_all(body);
    }
}

fn content_type(name: &str) -> &'static str {
    match name.rsplit('.').next().unwrap_or("") {
        "html" => "text/html; charset=utf-8",
        "js" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        _ => "application/octet-stream",
    }
}

fn open(url: &str) {
    let launched = if cfg!(target_os = "windows") {
        Command::new("cmd").args(["/C", "start", "", url]).spawn()
    } else if cfg!(target_os = "macos") {
        Command::new("open").arg(url).spawn()
    } else {
        Command::new("xdg-open").arg(url).spawn()
    };
    if launched.is_err() {
        println!("Open {url} in Chrome, Edge or Opera.");
    }
}

// Serves on a free port, asks for the app's pages, and checks they arrived.
fn selftest() -> i32 {
    let listener = match bind() {
        Some(l) => l,
        None => return 1,
    };
    let port = listener.local_addr().unwrap().port();
    thread::spawn(move || {
        for stream in listener.incoming().flatten() {
            serve(stream);
        }
    });
    let checks = [
        ("/", "<title>MultiDrop"),
        ("/app.js", "renderDevices"),
        ("/wire.js", "createWire"),
        ("/vendor/wireweave/src/wireweave.js", "createWireweave"),
    ];
    let mut all_ok = true;
    for (path, needle) in checks {
        let ok = fetch(port, path).map_or(false, |reply| reply.contains("200 OK") && reply.contains(needle));
        println!("{path}: {}", if ok { "ok" } else { "FAILED" });
        all_ok &= ok;
    }
    if all_ok { 0 } else { 1 }
}

fn fetch(port: u16, path: &str) -> Option<String> {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).ok()?;
    write!(stream, "GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").ok()?;
    let mut reply = String::new();
    stream.read_to_string(&mut reply).ok()?;
    Some(reply)
}
