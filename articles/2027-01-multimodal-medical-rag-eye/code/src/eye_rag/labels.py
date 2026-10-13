"""RFMiD label set: the 45 condition columns of the label CSVs, plus `Disease_Risk`.

The full names follow the RFMiD paper (Pachade et al., Data 2021); see docs/DATA.md.
The one-line visual descriptions are ours, written for the text encoder and the
prompts: what the finding looks like on a fundus photo, not diagnostic criteria.
"""

from __future__ import annotations

from dataclasses import dataclass

DISEASE_RISK = "Disease_Risk"
NORMAL = "NORMAL"  # pseudo-label for images with Disease_Risk == 0 (no condition)


@dataclass(frozen=True)
class Condition:
    code: str
    name: str
    description: str


CONDITIONS: tuple[Condition, ...] = (
    Condition("DR", "diabetic retinopathy", "microaneurysms, dot and blot hemorrhages and hard exudates"),
    Condition("ARMD", "age-related macular degeneration", "drusen, pigment changes or atrophy at the macula"),
    Condition("MH", "media haze", "a hazy, blurred view of the fundus caused by opacity of the eye's optical media"),
    Condition("DN", "drusen", "small yellow deposits beneath the retina"),
    Condition("MYA", "myopia", "a tessellated fundus with peripapillary atrophy and a tilted optic disc"),
    Condition("BRVO", "branch retinal vein occlusion", "flame-shaped hemorrhages in the sector drained by one retinal vein"),
    Condition("TSLN", "tessellation", "choroidal vessels visible through a thin retina, giving a tigroid pattern"),
    Condition("ERM", "epiretinal membrane", "a glistening membrane with surface wrinkling at the macula"),
    Condition("LS", "laser scars", "round pigmented scars from laser photocoagulation"),
    Condition("MS", "macular scar", "a scar at the macula"),
    Condition("CSR", "central serous retinopathy", "a round serous detachment of the retina at the macula"),
    Condition("ODC", "optic disc cupping", "an enlarged optic cup relative to the disc"),
    Condition("CRVO", "central retinal vein occlusion", "hemorrhages in all four quadrants with dilated, tortuous veins"),
    Condition("TV", "tortuous vessels", "abnormally twisted retinal vessels"),
    Condition("AH", "asteroid hyalosis", "many small refractile bodies floating in the vitreous"),
    Condition("ODP", "optic disc pallor", "a pale optic disc"),
    Condition("ODE", "optic disc edema", "a swollen optic disc with blurred margins"),
    Condition("ST", "optociliary shunt", "shunt vessels on the surface of the optic disc"),
    Condition("AION", "anterior ischemic optic neuropathy", "a swollen optic disc with disc hemorrhages"),
    Condition("PT", "parafoveal telangiectasia", "dilated capillaries and greyish retina around the fovea"),
    Condition("RT", "retinal traction", "retina pulled by fibrous tissue"),
    Condition("RS", "retinitis", "whitish areas of retinal inflammation"),
    Condition("CRS", "chorioretinitis", "patches of choroidal and retinal inflammation or scarring"),
    Condition("EDN", "exudation", "yellow exudates in the retina"),
    Condition("RPEC", "retinal pigment epithelium changes", "mottled pigmentation of the retinal pigment epithelium"),
    Condition("MHL", "macular hole", "a round, sharply outlined hole at the center of the macula"),
    Condition("RP", "retinitis pigmentosa", "bone-spicule pigmentation, narrowed vessels and a waxy pale disc"),
    Condition("CWS", "cotton-wool spots", "small fluffy white patches on the retina"),
    Condition("CB", "coloboma", "a missing sector of retina and choroid showing white sclera"),
    Condition("ODPM", "optic disc pit maculopathy", "a pit in the optic disc with fluid at the macula"),
    Condition("PRH", "preretinal hemorrhage", "a boat-shaped hemorrhage in front of the retina"),
    Condition("MNF", "myelinated nerve fibers", "white feathery patches along the nerve fibers near the disc"),
    Condition("HR", "hemorrhagic retinopathy", "widespread retinal hemorrhages"),
    Condition("CRAO", "central retinal artery occlusion", "a pale, whitened retina with a cherry-red spot at the fovea"),
    Condition("TD", "tilted disc", "an oval, obliquely oriented optic disc"),
    Condition("CME", "cystoid macular edema", "petal-shaped fluid cysts at the macula"),
    Condition("PTCR", "post-traumatic choroidal rupture", "a curved whitish streak concentric to the optic disc"),
    Condition("CF", "choroidal folds", "parallel light and dark lines across the posterior pole"),
    Condition("VH", "vitreous hemorrhage", "blood in the vitreous obscuring the view of the retina"),
    Condition("MCA", "macroaneurysm", "a round dilation of a retinal artery, often with hemorrhage or exudate"),
    Condition("VS", "vasculitis", "white sheathing along inflamed retinal vessels"),
    Condition("BRAO", "branch retinal artery occlusion", "whitened retina in the territory of one retinal artery"),
    Condition("PLQ", "plaque", "a bright embolic plaque inside a retinal artery"),
    Condition("HPED", "hemorrhagic pigment epithelial detachment", "a dark dome-shaped elevation of blood under the pigment epithelium"),
    Condition("CL", "collateral", "collateral vessels bypassing an occluded vessel"),
)

CODES: tuple[str, ...] = tuple(c.code for c in CONDITIONS)
BY_CODE: dict[str, Condition] = {c.code: c for c in CONDITIONS}

NORMAL_DESCRIPTION = "a healthy retina with a normal optic disc, macula and vessels"
