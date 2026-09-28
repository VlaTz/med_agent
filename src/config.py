"""Domain scope for this prototype -- mitochondrial medicine only (per ТЗ)."""

DEFAULT_DISEASES = [
    "Parkinson's disease",
    "Leber hereditary optic neuropathy (LHON)",
]

DEFAULT_DRUG_CLASSES = [
    "mitochondria-targeted antioxidants (MitoQ, SkQ1, elamipretide/SS-31)",
    "mitophagy/biogenesis modulators (urolithin A, NAD+ precursors)",
    "mtDNA gene therapy / mitochondrial replacement",
]

# Which drug classes are actually studied for which disease in this prototype's scope.
# Parkinson's disease is not itself caused by an mtDNA mutation, so mtDNA gene
# therapy/replacement isn't a real research direction there; LHON is a primary mtDNA
# disease, where gene therapy (e.g. lenadogene nolparvovec) is the headline experimental
# approach, while mitophagy/biogenesis modulators are comparatively little-studied for it.
DISEASE_DRUG_CLASSES = {
    "Parkinson's disease": [
        "mitochondria-targeted antioxidants (MitoQ, SkQ1, elamipretide/SS-31)",
        "mitophagy/biogenesis modulators (urolithin A, NAD+ precursors)",
    ],
    "Leber hereditary optic neuropathy (LHON)": [
        "mitochondria-targeted antioxidants (MitoQ, SkQ1, elamipretide/SS-31)",
        "mtDNA gene therapy / mitochondrial replacement",
    ],
}

DEFAULT_DATE_FROM = 2021  # ~3-5 year window per ТЗ

EXAMPLE_QUERIES = [
    "Сравни митохондриально-таргетные антиоксиданты со стандартной дофаминергической терапией при болезни Паркинсона: какие недавние исследования показывают реальную функциональную пользу?",
    "Как генная терапия мтДНК при LHON соотносится с поддерживающим стандартом лечения, и является ли она более перспективным направлением, чем антиоксидантные подходы?",
]
