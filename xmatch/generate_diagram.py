"""
Generates Graphviz DOT and standalone SVG diagram for the unified heterogeneous identity graph.
Shows :Record, :NAME, :EMAIL, and :PHONE nodes with structural and similarity edges.
"""

import os
import shutil

DOT_CONTENT = """digraph IdentityGraph {
    graph [rankdir=TB, bgcolor="#0d1117", fontname="Helvetica", pad="0.5", nodesep="0.6", ranksep="0.8"];
    node [fontname="Helvetica", fontsize=11, style="filled,rounded", shape=box, margin="0.15,0.1"];
    edge [fontname="Helvetica", fontsize=9, color="#8b949e", fontcolor="#8b949e"];

    // Subgraph: Source Records (Blue)
    subgraph cluster_records {
        label = "Source Touchpoint Records (:Record)";
        style = "dashed";
        color = "#58a6ff";
        fontcolor = "#58a6ff";
        fontsize = 13;

        r1 [label="Record 1\\nkaan\\nkpapaz@gmail\\n2696227", fillcolor="#1f293d", color="#388bfd", fontcolor="#e6edf3"];
        r2 [label="Record 2\\nkkaramete\\nkalles@gmail.com\\n5182696226", fillcolor="#1f293d", color="#388bfd", fontcolor="#e6edf3"];
        r3 [label="Record 3 (Centroid)\\nkaan karamete\\nkallespapaz@gmail\\n404356789", fillcolor="#1c3a5e", color="#58a6ff", penwidth=2, fontcolor="#58a6ff"];
        r4 [label="Record 4 (Isolated)\\ngulgun karamete\\ngkaramete@kmail.com\\n2696777", fillcolor="#21262d", color="#484f58", fontcolor="#8b949e"];
    }

    // Subgraph: Name Nodes (Green)
    subgraph cluster_names {
        label = "Name Attribute Nodes (:NAME)";
        style = "dashed";
        color = "#3fb950";
        fontcolor = "#3fb950";
        fontsize = 13;

        n1 [label="NAME: kaan", shape=ellipse, fillcolor="#122c1f", color="#2ea043", fontcolor="#7ee787"];
        n2 [label="NAME: kkaramete", shape=ellipse, fillcolor="#122c1f", color="#2ea043", fontcolor="#7ee787"];
        n3 [label="NAME: kaan karamete\\n[GOLDEN NAME - PR: 0.153]", shape=ellipse, fillcolor="#1b472e", color="#3fb950", penwidth=2.5, fontcolor="#aff5b4"];
        n4 [label="NAME: gulgun karamete", shape=ellipse, fillcolor="#21262d", color="#484f58", fontcolor="#8b949e"];
    }

    // Subgraph: Email Nodes (Orange)
    subgraph cluster_emails {
        label = "Email Attribute Nodes (:EMAIL)";
        style = "dashed";
        color = "#d29922";
        fontcolor = "#d29922";
        fontsize = 13;

        e1 [label="EMAIL: kpapaz@gmail", shape=note, fillcolor="#342411", color="#bb8009", fontcolor="#f0883e"];
        e2 [label="EMAIL: kalles@gmail.com", shape=note, fillcolor="#342411", color="#bb8009", fontcolor="#f0883e"];
        e3 [label="EMAIL: kallespapaz@gmail\\n[GOLDEN EMAIL - PR: 0.153]", shape=note, fillcolor="#4e3518", color="#d29922", penwidth=2.5, fontcolor="#ffd699"];
        e4 [label="EMAIL: gkaramete@kmail.com", shape=note, fillcolor="#21262d", color="#484f58", fontcolor="#8b949e"];
    }

    // Subgraph: Phone Nodes (Purple)
    subgraph cluster_phones {
        label = "Phone Attribute Nodes (:PHONE)";
        style = "dashed";
        color = "#a371f7";
        fontcolor = "#a371f7";
        fontsize = 13;

        p1 [label="PHONE: 2696227", shape=component, fillcolor="#2b1f3f", color="#8957e5", fontcolor="#d2a8ff"];
        p2 [label="PHONE: 5182696226\\n[GOLDEN PHONE - PR: 0.110]", shape=component, fillcolor="#3d2a5d", color="#a371f7", penwidth=2.5, fontcolor="#e2c5ff"];
        p3 [label="PHONE: 404356789", shape=component, fillcolor="#2b1f3f", color="#8957e5", fontcolor="#d2a8ff"];
        p4 [label="PHONE: 2696777", shape=component, fillcolor="#21262d", color="#484f58", fontcolor="#8b949e"];
    }

    // Structural Edges (Record -> Attribute)
    edge [color="#30363d", style="dotted", arrowsize=0.6];
    r1 -> n1 [label=":HAS_NAME"];
    r1 -> e1 [label=":HAS_EMAIL"];
    r1 -> p1 [label=":HAS_PHONE"];

    r2 -> n2 [label=":HAS_NAME"];
    r2 -> e2 [label=":HAS_EMAIL"];
    r2 -> p2 [label=":HAS_PHONE"];

    r3 -> n3 [label=":HAS_NAME"];
    r3 -> e3 [label=":HAS_EMAIL"];
    r3 -> p3 [label=":HAS_PHONE"];

    r4 -> n4 [label=":HAS_NAME"];
    r4 -> e4 [label=":HAS_EMAIL"];
    r4 -> p4 [label=":HAS_PHONE"];

    // Fuzzy Similarity Edges between Names (Green)
    edge [color="#3fb950", style="solid", penwidth=2, arrowsize=0.8, fontcolor="#7ee787"];
    n1 -> n3 [label="token_containment\\n(0.925)", dir=both];
    n2 -> n3 [label="initial_surname\\n(0.920)", dir=both];

    // Fuzzy Similarity Edges between Emails (Orange)
    edge [color="#d29922", style="solid", penwidth=2, arrowsize=0.8, fontcolor="#f0883e"];
    e1 -> e3 [label="subword_papaz\\n(0.820)", dir=both];
    e2 -> e3 [label="prefix_kalles\\n(0.882)", dir=both];

    // Fuzzy Similarity Edges between Phones (Purple)
    edge [color="#a371f7", style="solid", penwidth=2, arrowsize=0.8, fontcolor="#d2a8ff"];
    p1 -> p2 [label="suffix_1diff\\n(0.820)", dir=both];

    // Family Conflict Edge (Red / Blocked)
    edge [color="#f85149", style="dashed", penwidth=2.5, fontcolor="#f85149"];
    n4 -> n3 [label="FAMILY CONFLICT\\n(Penalty: 0.85)", dir=none];
}
"""


def generate_svg() -> str:
    """Produce a high-resolution, standalone SVG representation of the unified identity graph."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1150 780" width="100%" height="100%" style="background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
  <defs>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.5"/>
    </filter>
    <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#8b949e"/>
    </marker>
    <marker id="arrow-green" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#3fb950"/>
    </marker>
    <marker id="arrow-orange" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#d29922"/>
    </marker>
    <marker id="arrow-purple" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#a371f7"/>
    </marker>
  </defs>

  <!-- Title Header -->
  <text x="575" y="40" text-anchor="middle" fill="#58a6ff" font-size="22" font-weight="bold">FalkorDB Unified Heterogeneous Identity Graph</text>
  <text x="575" y="65" text-anchor="middle" fill="#8b949e" font-size="13">One Graph in GraphBLAS with :Record, :NAME, :EMAIL, and :PHONE Node Labels</text>

  <!-- ==================== RECORD NODES (TOP ROW) ==================== -->
  <!-- Record 1 -->
  <g transform="translate(60, 100)" filter="url(#shadow)">
    <rect width="210" height="90" rx="10" fill="#161b22" stroke="#388bfd" stroke-width="2"/>
    <text x="105" y="28" text-anchor="middle" fill="#58a6ff" font-size="14" font-weight="bold">(:Record {id: 1})</text>
    <text x="15" y="50" fill="#c9d1d9" font-size="11">name: 'kaan'</text>
    <text x="15" y="66" fill="#c9d1d9" font-size="11">email: 'kpapaz@gmail'</text>
    <text x="15" y="82" fill="#c9d1d9" font-size="11">phone: '2696227'</text>
  </g>

  <!-- Record 3 (Golden Centroid) -->
  <g transform="translate(470, 90)" filter="url(#shadow)">
    <rect width="230" height="110" rx="10" fill="#1c2d42" stroke="#58a6ff" stroke-width="3"/>
    <rect x="15" y="10" width="200" height="20" rx="4" fill="#1f6feb"/>
    <text x="115" y="24" text-anchor="middle" fill="#ffffff" font-size="11" font-weight="bold">ENTITY CENTROID (PR: 0.435)</text>
    <text x="115" y="50" text-anchor="middle" fill="#79c0ff" font-size="15" font-weight="bold">(:Record {id: 3})</text>
    <text x="15" y="72" fill="#e6edf3" font-size="11">name: 'kaan karamete'</text>
    <text x="15" y="88" fill="#e6edf3" font-size="11">email: 'kallespapaz@gmail'</text>
    <text x="15" y="104" fill="#e6edf3" font-size="11">phone: '404356789'</text>
  </g>

  <!-- Record 2 -->
  <g transform="translate(880, 100)" filter="url(#shadow)">
    <rect width="210" height="90" rx="10" fill="#161b22" stroke="#388bfd" stroke-width="2"/>
    <text x="105" y="28" text-anchor="middle" fill="#58a6ff" font-size="14" font-weight="bold">(:Record {id: 2})</text>
    <text x="15" y="50" fill="#c9d1d9" font-size="11">name: 'kkaramete'</text>
    <text x="15" y="66" fill="#c9d1d9" font-size="11">email: 'kalles@gmail.com'</text>
    <text x="15" y="82" fill="#c9d1d9" font-size="11">phone: '5182696226'</text>
  </g>

  <!-- Record 4 (Isolated / Family) -->
  <g transform="translate(470, 640)" filter="url(#shadow)">
    <rect width="230" height="90" rx="10" fill="#161b22" stroke="#f85149" stroke-width="1.5" stroke-dasharray="4"/>
    <text x="115" y="25" text-anchor="middle" fill="#f85149" font-size="13" font-weight="bold">(:Record {id: 4}) - Isolated Family</text>
    <text x="15" y="47" fill="#8b949e" font-size="11">name: 'gulgun karamete'</text>
    <text x="15" y="63" fill="#8b949e" font-size="11">email: 'gkaramete@kmail.com'</text>
    <text x="15" y="79" fill="#8b949e" font-size="11">phone: '2696777'</text>
  </g>

  <!-- ==================== NAME LAYER (:NAME) ==================== -->
  <text x="60" y="270" fill="#3fb950" font-size="14" font-weight="bold">Layer: :NAME</text>

  <!-- Name 1 -->
  <g transform="translate(70, 285)" filter="url(#shadow)">
    <rect width="190" height="50" rx="25" fill="#122c1f" stroke="#2ea043" stroke-width="2"/>
    <text x="95" y="26" text-anchor="middle" fill="#7ee787" font-size="12" font-weight="bold">(:NAME)</text>
    <text x="95" y="42" text-anchor="middle" fill="#e6edf3" font-size="11">'kaan'</text>
  </g>

  <!-- Name 3 (Golden Name) -->
  <g transform="translate(475, 275)" filter="url(#shadow)">
    <rect width="220" height="65" rx="30" fill="#184227" stroke="#3fb950" stroke-width="3"/>
    <text x="110" y="22" text-anchor="middle" fill="#aff5b4" font-size="10" font-weight="bold">★ GOLDEN NAME (PR: 0.153)</text>
    <text x="110" y="40" text-anchor="middle" fill="#7ee787" font-size="13" font-weight="bold">(:NAME)</text>
    <text x="110" y="56" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="bold">'kaan karamete'</text>
  </g>

  <!-- Name 2 -->
  <g transform="translate(890, 285)" filter="url(#shadow)">
    <rect width="190" height="50" rx="25" fill="#122c1f" stroke="#2ea043" stroke-width="2"/>
    <text x="95" y="26" text-anchor="middle" fill="#7ee787" font-size="12" font-weight="bold">(:NAME)</text>
    <text x="95" y="42" text-anchor="middle" fill="#e6edf3" font-size="11">'kkaramete'</text>
  </g>

  <!-- Name 4 -->
  <g transform="translate(200, 660)" filter="url(#shadow)">
    <rect width="190" height="50" rx="25" fill="#21262d" stroke="#8b949e" stroke-width="1.5"/>
    <text x="95" y="26" text-anchor="middle" fill="#8b949e" font-size="12" font-weight="bold">(:NAME)</text>
    <text x="95" y="42" text-anchor="middle" fill="#c9d1d9" font-size="11">'gulgun karamete'</text>
  </g>

  <!-- Name Similarities -->
  <path d="M 260 310 L 475 305" stroke="#3fb950" stroke-width="2.5" marker-end="url(#arrow-green)" marker-start="url(#arrow-green)"/>
  <rect x="300" y="292" width="135" height="20" rx="4" fill="#0d1117" stroke="#2ea043" stroke-width="1"/>
  <text x="367" y="306" text-anchor="middle" fill="#7ee787" font-size="10">token_containment (0.925)</text>

  <path d="M 890 310 L 695 305" stroke="#3fb950" stroke-width="2.5" marker-end="url(#arrow-green)" marker-start="url(#arrow-green)"/>
  <rect x="735" y="292" width="125" height="20" rx="4" fill="#0d1117" stroke="#2ea043" stroke-width="1"/>
  <text x="797" y="306" text-anchor="middle" fill="#7ee787" font-size="10">initial_surname (0.920)</text>

  <!-- Family Conflict Edge -->
  <path d="M 390 685 Q 585 580 585 340" stroke="#f85149" stroke-width="2.5" stroke-dasharray="6,4"/>
  <rect x="440" y="530" width="180" height="22" rx="4" fill="#321014" stroke="#f85149" stroke-width="1"/>
  <text x="530" y="545" text-anchor="middle" fill="#ff7b72" font-size="10" font-weight="bold">FAMILY CONFLICT (Penalty: 0.85)</text>

  <!-- ==================== EMAIL LAYER (:EMAIL) ==================== -->
  <text x="60" y="390" fill="#d29922" font-size="14" font-weight="bold">Layer: :EMAIL</text>

  <!-- Email 1 -->
  <g transform="translate(70, 405)" filter="url(#shadow)">
    <rect width="190" height="50" rx="6" fill="#2d1d0c" stroke="#bb8009" stroke-width="2"/>
    <text x="95" y="26" text-anchor="middle" fill="#f0883e" font-size="12" font-weight="bold">(:EMAIL)</text>
    <text x="95" y="42" text-anchor="middle" fill="#e6edf3" font-size="11">'kpapaz@gmail'</text>
  </g>

  <!-- Email 3 (Golden Email) -->
  <g transform="translate(475, 395)" filter="url(#shadow)">
    <rect width="220" height="65" rx="8" fill="#432c12" stroke="#d29922" stroke-width="3"/>
    <text x="110" y="22" text-anchor="middle" fill="#ffd699" font-size="10" font-weight="bold">★ GOLDEN EMAIL (PR: 0.153)</text>
    <text x="110" y="40" text-anchor="middle" fill="#f0883e" font-size="13" font-weight="bold">(:EMAIL)</text>
    <text x="110" y="56" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="bold">'kallespapaz@gmail'</text>
  </g>

  <!-- Email 2 -->
  <g transform="translate(890, 405)" filter="url(#shadow)">
    <rect width="190" height="50" rx="6" fill="#2d1d0c" stroke="#bb8009" stroke-width="2"/>
    <text x="95" y="26" text-anchor="middle" fill="#f0883e" font-size="12" font-weight="bold">(:EMAIL)</text>
    <text x="95" y="42" text-anchor="middle" fill="#e6edf3" font-size="11">'kalles@gmail.com'</text>
  </g>

  <!-- Email Similarities -->
  <path d="M 260 430 L 475 425" stroke="#d29922" stroke-width="2.5" marker-end="url(#arrow-orange)" marker-start="url(#arrow-orange)"/>
  <rect x="310" y="412" width="125" height="20" rx="4" fill="#0d1117" stroke="#bb8009" stroke-width="1"/>
  <text x="372" y="426" text-anchor="middle" fill="#f0883e" font-size="10">subword_papaz (0.820)</text>

  <path d="M 890 430 L 695 425" stroke="#d29922" stroke-width="2.5" marker-end="url(#arrow-orange)" marker-start="url(#arrow-orange)"/>
  <rect x="735" y="412" width="120" height="20" rx="4" fill="#0d1117" stroke="#bb8009" stroke-width="1"/>
  <text x="795" y="426" text-anchor="middle" fill="#f0883e" font-size="10">prefix_kalles (0.882)</text>

  <!-- ==================== PHONE LAYER (:PHONE) ==================== -->
  <text x="60" y="510" fill="#a371f7" font-size="14" font-weight="bold">Layer: :PHONE</text>

  <!-- Phone 1 -->
  <g transform="translate(70, 525)" filter="url(#shadow)">
    <polygon points="10,0 180,0 190,25 180,50 10,50 0,25" fill="#261a38" stroke="#8957e5" stroke-width="2"/>
    <text x="95" y="26" text-anchor="middle" fill="#d2a8ff" font-size="12" font-weight="bold">(:PHONE)</text>
    <text x="95" y="42" text-anchor="middle" fill="#e6edf3" font-size="11">'2696227'</text>
  </g>

  <!-- Phone 3 -->
  <g transform="translate(485, 525)" filter="url(#shadow)">
    <polygon points="10,0 190,0 200,25 190,50 10,50 0,25" fill="#261a38" stroke="#8957e5" stroke-width="2"/>
    <text x="100" y="26" text-anchor="middle" fill="#d2a8ff" font-size="12" font-weight="bold">(:PHONE)</text>
    <text x="100" y="42" text-anchor="middle" fill="#e6edf3" font-size="11">'404356789'</text>
  </g>

  <!-- Phone 2 (Golden Phone) -->
  <g transform="translate(875, 515)" filter="url(#shadow)">
    <polygon points="12,0 208,0 220,32 208,65 12,65 0,32" fill="#392454" stroke="#a371f7" stroke-width="3"/>
    <text x="110" y="22" text-anchor="middle" fill="#e2c5ff" font-size="10" font-weight="bold">★ GOLDEN PHONE (PR: 0.110)</text>
    <text x="110" y="40" text-anchor="middle" fill="#d2a8ff" font-size="13" font-weight="bold">(:PHONE)</text>
    <text x="110" y="56" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="bold">'5182696226' (10-Digit)</text>
  </g>

  <!-- Phone Similarity: Curved line from P1 to P2 -->
  <path d="M 165 575 C 165 620, 985 620, 985 580" fill="none" stroke="#a371f7" stroke-width="2.5" marker-end="url(#arrow-purple)" marker-start="url(#arrow-purple)"/>
  <rect x="510" y="600" width="130" height="20" rx="4" fill="#0d1117" stroke="#8957e5" stroke-width="1"/>
  <text x="575" y="614" text-anchor="middle" fill="#d2a8ff" font-size="10">suffix_1diff (0.820)</text>

  <!-- ==================== RECORD TO ATTRIBUTE EDGES ==================== -->
  <!-- R1 links -->
  <path d="M 165 190 L 165 285" stroke="#388bfd" stroke-dasharray="3,3" stroke-width="1.5"/>
  <path d="M 130 190 C 130 240, 90 350, 110 405" stroke="#388bfd" stroke-dasharray="3,3" stroke-width="1.5"/>
  <path d="M 100 190 C 80 250, 40 450, 90 525" stroke="#388bfd" stroke-dasharray="3,3" stroke-width="1.5"/>

  <!-- R3 links -->
  <path d="M 585 200 L 585 275" stroke="#58a6ff" stroke-dasharray="3,3" stroke-width="2"/>
  <path d="M 585 340 L 585 395" stroke="#58a6ff" stroke-dasharray="3,3" stroke-width="2"/>
  <path d="M 585 460 L 585 525" stroke="#58a6ff" stroke-dasharray="3,3" stroke-width="2"/>

  <!-- R2 links -->
  <path d="M 985 190 L 985 285" stroke="#388bfd" stroke-dasharray="3,3" stroke-width="1.5"/>
  <path d="M 1020 190 C 1020 240, 1050 350, 1040 405" stroke="#388bfd" stroke-dasharray="3,3" stroke-width="1.5"/>
  <path d="M 1050 190 C 1070 250, 1100 450, 1050 515" stroke="#388bfd" stroke-dasharray="3,3" stroke-width="1.5"/>

</svg>
"""
    return svg


def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    dot_path = os.path.join(root_dir, "identity_graph.dot")
    svg_path = os.path.join(root_dir, "identity_graph.svg")

    with open(dot_path, "w", encoding="utf-8") as f:
        f.write(DOT_CONTENT)
    print(f"Generated DOT file: {dot_path}")

    svg_content = generate_svg()
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated SVG file: {svg_path}")

    # Also copy to artifact directory if available
    artifact_dir = "/home/bkaramete/.gemini/antigravity-cli/brain/79da60fb-6f44-482b-9b77-36d1786c7679"
    if os.path.exists(artifact_dir):
        artifact_svg = os.path.join(artifact_dir, "identity_graph.svg")
        shutil.copy(svg_path, artifact_svg)
        print(f"Copied SVG to artifact dir: {artifact_svg}")


if __name__ == "__main__":
    main()
