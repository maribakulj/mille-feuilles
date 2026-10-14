#!/usr/bin/env python3
"""Write the original demonstration documents of the multi-document import example.

Texts are original (Claude, 14 October 2026, CC0-1.0): fictional towns, people and
events, no historical document reused. Each body document follows one subject from
paragraph to paragraph, so that consecutive units stay on that subject. Run once from
this directory; it refuses to overwrite a different existing file.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATE = "2026-10-14"

GROUPS = {
    "velmont": {
        "body-pont": [
            "Les crues de la semaine dernière ont emporté deux arches du vieux pont de Velmont. Depuis lundi, les habitants de la rive gauche gagnent le marché par le bac du passeur, qui ne peut prendre que six personnes à la fois. Le maire a réuni le conseil dès mardi soir pour examiner les moyens de rétablir le passage avant l’hiver.",
            "L’ingénieur du département est venu mesurer les piles restées debout. Selon son premier rapport, la troisième pile a perdu une partie de ses fondations et devra être reprise entièrement. Les deux autres paraissent solides ; elles pourront porter une travée provisoire en charpente, si le bois est livré avant la fin du mois.",
            "Le conseil a voté jeudi un crédit de quatre mille francs pour la passerelle provisoire. Les charpentiers de la ville se sont offerts à travailler sans relâche, à la condition que les scieries de la vallée fournissent les poutres en priorité. Le préfet sera sollicité pour une subvention destinée à la reconstruction en pierre.",
            "Les premières poutres sont arrivées samedi sur des voitures à bœufs. On les a déchargées sur la grève, où les ouvriers les équarrissent à la hache. Le passeur continue son service, mais il annonce qu’il suspendra les traversées dès que l’eau montera de nouveau au-dessus de la seconde marque de l’échelle.",
            "La passerelle a été ouverte dimanche aux piétons, en présence du conseil municipal et d’une foule nombreuse. Les voitures devront encore attendre ; le garde champêtre veille à ce qu’aucune charrette ne s’y engage. Les travaux de la pile détruite commenceront au printemps, lorsque la rivière aura retrouvé son lit ordinaire.",
        ],
        "body-ecole": [
            "La nouvelle école de garçons de Velmont ouvrira ses portes à la rentrée d’octobre. Le bâtiment, élevé sur l’ancien jardin du presbytère, comprend deux classes claires, un préau couvert et le logement de l’instituteur. Les familles des hameaux attendaient depuis longtemps une salle plus vaste que la grange louée jusqu’ici.",
            "Les menuisiers achèvent les tables et les bancs, taillés dans le chêne d’une coupe communale. Chaque table recevra deux encriers de faïence et un casier pour les livres. Le directeur a demandé que les fenêtres soient garnies de rideaux, afin que les élèves du premier rang ne soient pas éblouis par le soleil de l’après-midi.",
            "Le conseil municipal a fixé à soixante-dix le nombre des élèves admis. Les inscriptions seront reçues à la mairie chaque matin de la semaine prochaine. Les parents devront présenter l’extrait de naissance de l’enfant et un certificat de vaccine ; les enfants des fermes éloignées pourront déjeuner au préau, sous la surveillance du maître adjoint.",
            "Une petite bibliothèque scolaire sera installée dans l’armoire du vestibule. Plusieurs habitants ont déjà offert des ouvrages de géographie, d’histoire naturelle et de lecture courante. Le directeur prêtera ces livres le samedi, pour une semaine, aux élèves qui auront tenu leurs cahiers avec soin pendant le mois écoulé.",
            "L’inauguration aura lieu le premier dimanche d’octobre, à deux heures. La fanfare précédera le cortège depuis la place de la mairie jusqu’à la cour de l’école. Après la remise des clés, le maire distribuera aux enfants des plumes et des ardoises neuves, et les familles pourront visiter les classes jusqu’au soir.",
        ],
        "title": [
            "LE PONT DE VELMONT",
            "Nouvelles de la rivière",
            "AU CONSEIL MUNICIPAL",
            "La rentrée des classes",
            "CHRONIQUE LOCALE",
            "Travaux publics",
            "L’ÉCOLE NEUVE",
            "Faits divers",
        ],
        "advertisement": [
            "BOIS DE CHARPENTE — Scierie Delorme, au moulin d’aval. Poutres de chêne et de sapin, livraison par voiture dans tout le canton. Prix modérés.",
            "À VENDRE — Une barque de passeur en bon état, avec ses avirons et sa chaîne. S’adresser au bureau du journal.",
            "LIBRAIRIE MARTEAU, rue du Marché. Cahiers, plumes, encres et livres de classe pour la rentrée. Remise aux instituteurs.",
            "ON DEMANDE un ouvrier charpentier sachant équarrir, pour travaux d’hiver. Logement assuré. Se présenter au chantier du pont.",
        ],
    },
    "castelbrune": {
        "body-foire": [
            "La foire de la Saint-Martin s’est tenue mardi à Castelbrune, par un temps sec et froid. Dès l’aube, les éleveurs des plateaux sont descendus avec leurs troupeaux, et le champ de foire était entièrement occupé avant sept heures. On estime à plus de neuf cents le nombre des bêtes amenées, chiffre que l’on n’avait pas vu depuis plusieurs années.",
            "Les bœufs de travail ont été très recherchés. Les marchands venus de la plaine ont payé les paires bien appareillées jusqu’à huit cents francs, et quelques ventes se sont conclues avant même l’ouverture officielle. Les jeunes veaux, au contraire, se sont vendus lentement, les acheteurs trouvant les prix demandés trop élevés pour la saison.",
            "Sur la place de l’église, les marchands de toile et de quincaillerie avaient dressé leurs étalages. Les fermières y ont acheté des couvertures, des chaudrons et des outils pour l’hiver. Un colporteur proposait des almanachs et des images coloriées, qu’il vendait deux sous la pièce aux enfants rassemblés autour de sa voiture.",
            "Le commissaire de police signale que la journée s’est passée sans désordre notable. Seule une jument effrayée par le bruit d’une crécelle s’est échappée vers la route de la gare ; elle a été rattrapée près du lavoir par deux garçons du village, que son propriétaire a récompensés d’une pièce blanche.",
            "Le soir, les auberges étaient pleines et l’on dansait dans la grande salle du Lion d’Or. Les éleveurs sont repartis le lendemain matin, satisfaits pour la plupart de leurs affaires. Le conseil municipal étudie l’agrandissement du champ de foire, devenu trop étroit pour une affluence semblable.",
        ],
        "body-incendie": [
            "Un incendie a éclaté dans la nuit de jeudi à vendredi dans une grange du faubourg de Castelbrune. Le feu, parti d’un tas de fourrage, s’est communiqué en quelques minutes à la toiture de chaume. Le propriétaire, réveillé par les aboiements de son chien, a pu faire sortir les chevaux de l’écurie voisine avant que les flammes ne l’atteignent.",
            "La cloche de l’église a sonné le tocsin vers une heure du matin. Les pompiers sont arrivés avec la pompe à bras, suivis d’une cinquantaine d’habitants qui ont formé la chaîne depuis la fontaine du carrefour. Il a fallu plus de deux heures pour se rendre maître du feu, que le vent d’est poussait vers les maisons de la rue Basse.",
            "La grange est entièrement détruite, ainsi que la récolte de foin qu’elle contenait. La maison d’habitation a été préservée, grâce au mur de pierre qui la sépare de la grange. On évalue les pertes à environ trois mille francs ; le propriétaire était heureusement assuré auprès d’une compagnie de la ville.",
            "L’enquête du brigadier de gendarmerie n’a relevé aucun indice de malveillance. On pense que le fourrage, rentré un peu humide après les dernières pluies, s’est échauffé jusqu’à prendre feu. Les cultivateurs sont invités à surveiller leurs meules et à ne rentrer le foin que parfaitement sec.",
            "Le maire a adressé publiquement ses remerciements aux pompiers et aux habitants accourus. Il rappelle que la pompe communale a besoin d’un tuyau neuf, et qu’une souscription est ouverte à la mairie pour en faire l’achat. Les premiers dons ont été versés dès samedi par les voisins du sinistré.",
        ],
        "title": [
            "LA FOIRE DE LA SAINT-MARTIN",
            "Nouvelles agricoles",
            "UN INCENDIE AU FAUBOURG",
            "Chronique de Castelbrune",
            "MARCHÉS ET FOIRES",
            "Informations diverses",
            "AVIS AUX CULTIVATEURS",
            "Dernière heure",
        ],
        "advertisement": [
            "COMPAGNIE D’ASSURANCES contre l’incendie. Agence de Castelbrune, place de l’Église. Bâtiments, récoltes et bestiaux. Renseignements gratuits.",
            "À VENDRE — Une paire de bœufs de cinq ans, bien appareillés, dressés au joug. S’adresser au fermier de la Brosse.",
            "QUINCAILLERIE BERTIN. Chaudrons, seaux, outils de culture, poêles de fonte. Grand choix pour l’hiver.",
            "PERDU, le jour de la foire, un fouet à manche de houx garni de cuivre. Le rapporter au Lion d’Or ; récompense.",
        ],
    },
    "lisserand": {
        "body-vendanges": [
            "Les vendanges ont commencé lundi dans les coteaux de Lisserand. Le ban avait été fixé par le conseil après la visite des vignes, où le raisin a été jugé mûr sur toutes les pentes exposées au midi. Dès le matin, les équipes de coupeurs se sont mises en route, suivies des charrettes chargées de comportes vides.",
            "La récolte s’annonce abondante, malgré la grêle qui avait frappé quelques parcelles au mois de juillet. Les grappes sont saines et serrées ; on ne signale presque aucune trace de pourriture. Les vieux vignerons assurent que l’on n’avait pas vu une telle quantité depuis l’année de la grande comète.",
            "La main-d’œuvre est venue en partie des villages de la montagne. Les coupeurs sont logés dans les granges et nourris à la ferme ; ils reçoivent un franc cinquante par journée. Le soir, on entend des chants dans les cours, où les porteurs vident les comportes dans les cuves avant de regagner leur paille.",
            "Le prix du vin nouveau n’est pas encore établi. Les négociants de la ville attendent la fin du pressurage pour faire leurs offres, et les propriétaires hésitent à vendre avant d’avoir goûté le moût. Plusieurs d’entre eux préparent des fûts neufs, dans l’espoir de garder une partie de la récolte jusqu’au printemps.",
            "Les vendanges devraient s’achever à la fin de la semaine prochaine si le beau temps persiste. Selon l’usage, la dernière charrette sera ornée d’un bouquet de feuillage, et un repas réunira coupeurs et propriétaires dans la grande salle de la mairie. La fanfare de Lisserand a promis son concours à cette fête.",
        ],
        "body-societe": [
            "Une société de secours mutuels vient d’être fondée à Lisserand par les ouvriers des tanneries et quelques artisans de la ville. Ses statuts ont été approuvés par le préfet le mois dernier. Elle se propose de venir en aide à ses membres en cas de maladie, d’accident ou de chômage forcé.",
            "La cotisation est fixée à un franc par mois. En retour, le sociétaire malade reçoit une indemnité d’un franc par jour pendant trois mois au plus, ainsi que les visites gratuites du médecin de la société. Les remèdes prescrits sont payés sur la caisse commune, sur présentation de l’ordonnance au trésorier.",
            "Le bureau a été élu dimanche dans la salle de la justice de paix. Le président est un maître tanneur estimé ; le secrétaire et le trésorier ont été choisis parmi les ouvriers. Le bureau se réunira le premier lundi de chaque mois pour examiner les demandes de secours et vérifier les comptes.",
            "Les membres honoraires, qui versent une cotisation sans prétendre aux secours, sont déjà au nombre de vingt. Le docteur de la ville a accepté de soigner les sociétaires à un prix réduit, et le pharmacien consent une remise sur les médicaments. Ces concours permettent d’espérer une caisse solide dès la première année.",
            "La société compte aujourd’hui quatre-vingt-trois membres actifs. Elle prépare un règlement pour les funérailles de ses membres, auxquelles tous les sociétaires seront invités à assister. Les ouvriers qui souhaitent adhérer peuvent se faire inscrire chez le secrétaire, rue des Tanneurs, chaque soir après sept heures.",
        ],
        "title": [
            "LES VENDANGES",
            "Nouvelles du vignoble",
            "SECOURS MUTUELS",
            "Chronique de Lisserand",
            "LE MARCHÉ DES VINS",
            "Bulletin du canton",
            "VIE OUVRIÈRE",
            "Échos et nouvelles",
        ],
        "advertisement": [
            "TONNELLERIE GARNIER. Fûts neufs de chêne, comportes, cuves. Réparations promptes pendant les vendanges.",
            "ON DEMANDE des coupeurs et des porteurs pour les vendanges. Nourris et logés. S’adresser au domaine des Combes.",
            "PHARMACIE CENTRALE, place du Marché. Remise aux membres des sociétés de secours mutuels sur présentation de leur livret.",
            "À LOUER — Un cellier voûté avec pressoir, près de la route des coteaux. Entrée en jouissance immédiate.",
        ],
    },
    "hautbrume": {
        "body-chemin-de-fer": [
            "Les travaux de la ligne de chemin de fer qui doit relier Hautbrume à la vallée ont repris cette semaine. Les terrassiers ont attaqué la tranchée du col, où la roche se montre plus dure que les ingénieurs ne l’avaient prévu. On travaille désormais à la poudre, et les habitants des fermes voisines ont été priés de tenir leurs bêtes à l’écart.",
            "Près de trois cents ouvriers sont employés sur le chantier. Beaucoup viennent des départements voisins et logent dans des baraquements de planches élevés le long du tracé. Une cantine leur sert la soupe deux fois par jour, et le curé du village a obtenu qu’une messe soit dite pour eux le dimanche dans la chapelle du hameau.",
            "Le viaduc qui doit franchir le ravin des Saules est la partie la plus difficile de l’ouvrage. Ses piles, hautes de trente mètres, s’élèvent lentement ; les maçons y montent les pierres au moyen d’une grue à vapeur, que les enfants du pays viennent regarder chaque jeudi. On compte achever les arches avant les premières neiges.",
            "Un accident s’est produit mercredi dans la tranchée : un bloc détaché par une mine a blessé deux ouvriers à la jambe. Ils ont été transportés à l’hospice de Hautbrume, où le médecin juge leur état rassurant. L’entrepreneur a fait renforcer les étais et interdit l’approche du front de taille pendant les tirs.",
            "Si les travaux ne subissent pas de nouveau retard, la ligne pourrait être ouverte aux voyageurs au début de l’été prochain. Les commerçants de Hautbrume se réjouissent déjà de pouvoir recevoir leurs marchandises en quelques heures, au lieu des deux journées de voiture qu’exige aujourd’hui la route du col.",
        ],
        "body-hiver": [
            "La neige est tombée en abondance sur Hautbrume dans la nuit de dimanche. Au matin, la couche atteignait soixante centimètres sur la place, et bien davantage dans les rues exposées au vent du nord. Les habitants ont dû dégager eux-mêmes le seuil de leurs maisons avant de pouvoir sortir.",
            "La route du col est fermée depuis lundi. La voiture de la poste n’a pu dépasser le hameau des Granges, et le courrier a été porté à dos de mulet jusqu’à la ville. Les cantonniers, aidés d’hommes de bonne volonté, ouvrent une tranchée dans les congères ; ils espèrent rétablir le passage avant la fin de la semaine.",
            "Le froid a été très vif mardi et mercredi. La fontaine de la place a gelé, et les ménagères vont puiser l’eau au lavoir couvert, où une source tiède ne gèle jamais. Le bureau de bienfaisance a fait distribuer du bois de chauffage aux familles les plus pauvres, sur la liste dressée par les conseillers de chaque quartier.",
            "Les enfants ont trouvé dans la neige un divertissement inattendu. Les pentes du pré communal sont couvertes de luges, et l’instituteur a dû rappeler que l’école ne ferme pas pour autant. Plusieurs élèves des hameaux éloignés n’ont pourtant pu venir en classe, le chemin étant impraticable pour de jeunes enfants.",
            "Le dégel s’est annoncé vendredi par un vent du sud. Les toits se déchargent de leur neige avec fracas, et les passants sont priés de prendre garde aux chutes. Le maire recommande de dégager les caniveaux, afin que l’eau de fonte ne pénètre pas dans les caves des maisons basses.",
        ],
        "title": [
            "LA LIGNE DU COL",
            "Travaux du chemin de fer",
            "L’HIVER À HAUTBRUME",
            "Nouvelles de la montagne",
            "LA ROUTE FERMÉE",
            "Chronique régionale",
            "AU CHANTIER DU VIADUC",
            "Bulletin météorologique",
        ],
        "advertisement": [
            "BOIS DE CHAUFFAGE — Hêtre et chêne sciés, rendus à domicile. Commandes chez Marchal, au bas de la Grand-Rue.",
            "ON DEMANDE des terrassiers et des maçons pour les travaux de la ligne. S’adresser au bureau de l’entreprise, route du col.",
            "SABOTS ET GALOCHES pour l’hiver, chez Roux, cordonnier. Fourrures et chaussons de laine.",
            "AVIS — Le service de la poste par mulet partira chaque matin à six heures tant que la route restera fermée.",
        ],
    },
    "corvelle": {
        "body-port": [
            "Le petit port de Corvelle a connu cette semaine une animation inaccoutumée. Une flottille de six bateaux de pêche, revenue des bancs du large, a débarqué une quantité considérable de harengs. Les femmes des pêcheurs ont travaillé toute la nuit sur le quai à les trier et à les ranger dans les barils de saumure.",
            "Les mareyeurs de la ville voisine sont accourus dès la nouvelle connue. Ils ont acheté le poisson frais à bon prix et l’ont expédié par la première voiture vers les marchés de l’intérieur. Le reste a été salé dans les magasins du port, où les tonneliers ne suffisaient plus à fournir les barils.",
            "La pêche n’a pas été sans danger. Un coup de vent, dans la nuit de mercredi, a obligé les équipages à se mettre à la cape pendant plusieurs heures. Un mousse a été blessé à la main par une manœuvre ; il a été soigné à son retour par le médecin du port, qui ne craint aucune suite.",
            "Les anciens rappellent que de pareilles prises étaient fréquentes autrefois, avant que les bancs ne s’éloignent de la côte. Ils y voient le signe d’une bonne saison et conseillent aux jeunes patrons de réparer leurs filets sans tarder, afin de pouvoir repartir dès que la mer le permettra.",
            "La municipalité profitera des recettes de l’octroi pour faire curer l’entrée du port, envasée depuis les tempêtes de l’hiver dernier. Les travaux commenceront à la prochaine grande marée. Pendant ce temps, les bateaux devront attendre la pleine mer pour franchir la passe.",
        ],
        "body-concours": [
            "Le concours musical de Corvelle a réuni dimanche une vingtaine de sociétés venues de toute la région. Dès le matin, les fanfares et les harmonies ont défilé dans les rues pavoisées, depuis la gare jusqu’à la place du Marché, où un kiosque avait été dressé pour l’occasion.",
            "Les épreuves de lecture à vue se sont déroulées dans la salle des fêtes. Chaque société recevait un morceau inconnu, qu’elle devait exécuter après dix minutes d’étude. Le jury, présidé par un professeur du conservatoire de la ville voisine, a noté avec sévérité la justesse et la mesure.",
            "L’après-midi, les exécutions d’honneur ont attiré une foule considérable. L’harmonie des tanneurs de Lisserand a été particulièrement applaudie pour son ouverture, conduite avec beaucoup d’entrain. La fanfare de Corvelle, qui jouait hors concours, a terminé la séance par une marche de son chef.",
            "Les prix ont été distribués à six heures par le maire, sous le kiosque illuminé. Trois premiers prix et une palme d’excellence ont été décernés ; chaque lauréat a reçu une médaille de vermeil et un diplôme. Les musiciens ont été ensuite reçus à un vin d’honneur offert par la municipalité.",
            "La soirée s’est terminée par un bal sur la place et un feu d’artifice tiré depuis la jetée. Les trains spéciaux ont ramené les sociétés dans la nuit. Le comité d’organisation remercie les habitants qui ont logé les musiciens et ceux qui ont décoré leurs façades.",
        ],
        "title": [
            "LE RETOUR DES PÊCHEURS",
            "Nouvelles du port",
            "LE CONCOURS MUSICAL",
            "Chronique de Corvelle",
            "MOUVEMENT DU PORT",
            "Fêtes et réjouissances",
            "LA SAISON DE PÊCHE",
            "Dernières nouvelles",
        ],
        "advertisement": [
            "FILETS ET CORDAGES — Maison Le Bihan, sur le quai. Réparations de voiles et de filets en vingt-quatre heures.",
            "À VENDRE — Un canot de pêche de six mètres, gréé, avec ses filets. S’adresser au patron Guillou.",
            "HÔTEL DU COMMERCE, face à la gare. Chambres confortables, table d’hôte, prix spéciaux pour les sociétés musicales.",
            "SEL DE MER pour salaisons, en sacs de cinquante kilos. Dépôt au magasin du port.",
        ],
    },
}

NOTICE = """# Textes originaux de démonstration — import multi-documents

Les documents de ce dossier ont été rédigés le 14 octobre 2026 par l’assistant
Claude pour Mille Feuilles. Ils sont synthétiques, sans reprise d’un journal,
d’un corpus OCR ou d’une page de test. Les villes (Velmont, Castelbrune,
Lisserand, Hautbrume, Corvelle), personnes, entreprises, avis et événements sont
fictifs et ne constituent pas une source historique.

Ces textes sont dédiés au domaine public sous **CC0 1.0 Universal**, dans toute
la mesure des droits qui pourraient y exister. La dédicace porte sur les
documents de ce dossier seulement. Source officielle :
<https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt>.

Chaque document de corps suit un seul sujet sur cinq paragraphes, afin que des
paragraphes consécutifs restent sur ce sujet. Cette cohérence est rédactionnelle
et non mesurée ; le petit volume et l’origine synthétique ne justifient aucune
représentativité de la presse du XIXe siècle ni aucun gain OCR ou de segmentation.
"""


def write(path: Path, text: str) -> None:
    data = unicodedata.normalize("NFC", text).encode("utf-8")
    if path.exists() and path.read_bytes() != data:
        raise SystemExit(f"Refus : fichier existant différent {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main() -> None:
    write(HERE / "NOTICE.md", NOTICE)
    rows = []
    for group, documents in GROUPS.items():
        for name, units in documents.items():
            role = "body" if name.startswith("body") else name
            separator = "\n" if role == "title" else "\n\n"
            document_id = f"mf-presse-multi-{group}-{name}"
            relative = f"documents/{group}-{name}.txt"
            write(HERE / relative, separator.join(units) + "\n")
            rows.append({
                "content_type": "original_synthetic_demonstration", "date": DATE,
                "historical_corpus": False, "language": "fr", "path": relative,
                "rights": {"attribution": "Textes originaux rédigés par Claude pour Mille Feuilles, 14 octobre 2026",
                           "evidence_path": "NOTICE.md", "license": "CC0-1.0",
                           "redistribution_allowed": True, "status": "verified"},
                "role": role, "source_document_id": document_id,
                "source_group_id": f"mf-presse-multi-{group}",
                "source_uri": f"urn:mille-feuilles:original:{document_id}",
            })
    write(HERE / "import.jsonl",
          "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


if __name__ == "__main__":
    main()
