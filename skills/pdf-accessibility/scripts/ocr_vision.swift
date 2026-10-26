// macOS OCR backend for ocr.py: Apple Vision "accurate" text recognition, fully on-device.
//
// Usage: swift ocr_vision.swift PAGE.png LANG [LANG ...]   (normally called by ocr.py --engine vision)
// Prints JSON to stdout: [{"text", "conf", "box": [x0, top, x1, bottom]}] in image pixels, top-based.
//
// Vision reports normalized bottom-left boxes; they are converted here so ocr.py can treat
// every engine the same. Language correction is off so names, numbers and source typos are
// kept as printed. Vision is often better than Tesseract on small print in slide exports.
// If it fails with a CVPixelBuffer or sandbox error, the process lacks OS access: rerun it
// with the needed permission or use --engine tesseract. Never fall back to an online OCR.
import AppKit
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count >= 2, let image = NSImage(contentsOfFile: args[1]),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("usage: ocr_vision.swift PAGE.png [LANG ...]\n".data(using: .utf8)!)
    exit(2)
}
let w = Double(cg.width), h = Double(cg.height)
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
req.recognitionLanguages = args.count > 2 ? Array(args[2...]) : ["en-US"]
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
var out: [[String: Any]] = []
for ob in req.results ?? [] {
    guard let c = ob.topCandidates(1).first else { continue }
    let b = ob.boundingBox
    out.append(["text": c.string, "conf": Double(c.confidence) * 100,
                "box": [b.minX * w, (1 - b.maxY) * h, b.maxX * w, (1 - b.minY) * h]])
}
let data = try JSONSerialization.data(withJSONObject: out, options: [])
FileHandle.standardOutput.write(data)
