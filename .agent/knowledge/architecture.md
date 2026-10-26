# ZenExport: ανάλυση και αρχιτεκτονική

Ημερομηνία ελέγχου: 2026-10-23. Βάση: το υπάρχον working tree, μαζί με τις
προϋπάρχουσες αλλαγές σε attributes, visibility και εξαγωγή ανά component.

## Τι επιβεβαιώθηκε και τι παραμένει ανοιχτό

Εξετάστηκε ο προηγούμενος μονολιθικός κώδικας, το configuration, τα manifests και
το installer. Διαβάστηκαν επίσης οι κοινές οδηγίες των Fusion projects και η δομή
του ZenParams. Δεν εισάγεται κώδικας από άλλα projects: κάθε add-in παραμένει αυτόνομο.

Οι 63 αυτοματοποιημένες δοκιμές πέρασαν σε Python 3.11 και 3.13. Πέρασαν lint,
έλεγχος σύνταξης και δημιουργία ZIP bundle. Ελέγχθηκαν 65 μέλη του εγκατεστημένου
Fusion API μέσω των τοπικών Python bindings. Οι προσομοιώσεις δεν αποδεικνύουν
ότι οι native translators λειτουργούν σωστά στο Fusion. Δεν εκτελέστηκε live export,
έλεγχος επανεισαγωγής F3D/STEP ή εγκατάσταση MSI. Δεν υπάρχει μέτρηση πραγματικής
επιτάχυνσης και δεν αποδίδεται αυθαίρετο ποσοστό απόδοσης.

## Πώς λειτουργούσε η έκδοση που ελέγχθηκε

Το `ZenExport.py` καταχωρούσε μία command definition και παρακολουθούσε native Save
commands. Ακύρωνε το Save και καλούσε αμέσως την εξαγωγή. Αναζητούσε προορισμό
στα attributes και σε JSON, με fallback σε revision ID και όνομα εγγράφου.
Υπολόγιζε μία συμβολοσειρά από counts του timeline, occurrences και παραμέτρων,
μαζί με το Python hash ονομάτων/visibility. Αν ταίριαζε με την προηγούμενη,
παρέλειπε την εξαγωγή. Διαφορετικά δημιουργούσε CAD/vNN, έγραφε F3D και STEP,
αντικαθιστούσε αρχεία στο κοινό Models, ενημέρωνε context/hash και άνοιγε φάκελο.

## Ευρήματα του προηγούμενου κώδικα

| Προτεραιότητα | Επιβεβαιωμένο εύρημα | Συνέπεια |
| --- | --- | --- |
| Κρίσιμη | Counts και visibility δεν περιλαμβάνουν τιμές παραμέτρων, μετασχηματισμούς και πραγματική γεωμετρία. Το exception fallback είναι η σταθερά ERROR. | Πραγματική αλλαγή μπορεί να θεωρηθεί αμετάβλητο σχέδιο και να μη δημιουργηθεί backup. |
| Κρίσιμη | Το τελευταίο hash ενημερώνεται ακόμη κι όταν exports αποτυγχάνουν. | Η επόμενη προσπάθεια μπορεί να παραλειφθεί, παρότι δεν υπάρχει πλήρες backup. |
| Υψηλή | Η αποφυγή διπλοτύπων βασίζεται σε component/body names. | Διαφορετικά αντικείμενα με ίδιο ή ισοδύναμο sanitized όνομα παραλείπονται. |
| Υψηλή | Το revisionId χρησιμοποιείται ως ταυτότητα. | Μεταβάλλεται με αλλαγές του component και δημιουργεί ασθενές binding/πολλά παλιά keys. |
| Υψηλή | Το native Save ακυρώνεται πριν ελεγχθεί ότι υπάρχει Design. | Μπορεί να εμποδιστεί Save σε άλλο ενεργό product. |
| Υψηλή | Τα attributes γράφονται μετά την εξαγωγή του archive. | Το πρώτο F3D δεν περιέχει το νέο binding. |
| Υψηλή | Models και preview είναι κοινά για όλες τις εκδόσεις. | Αντικαθίστανται, ενώ παλιά meshes για αφαιρεμένα bodies μπορούν να παραμείνουν. |
| Υψηλή | Το stop δεν αφαιρεί event subscriptions. | Κίνδυνος παραμένουσας συμπεριφοράς και πολλαπλών callbacks μετά από reload. |
| Μεσαία | Το built-in hash δεν είναι σταθερό μεταξύ διαφορετικών Python processes. | Δεν αποτελεί αξιόπιστη αποθηκευμένη υπογραφή. |
| Μεσαία | Σφάλματα config και πολλών API calls αγνοούνται. | Αποτυχίες δεν γίνονται διαγνώσιμες. Η εγγραφή δίπλα στο εγκατεστημένο πρόγραμμα μπορεί επίσης να αποτύχει λόγω δικαιωμάτων. |
| Μεσαία | Το prompt λέει all documents, ενώ εξάγεται μόνο το ενεργό Design. | Παραπλανητική περιγραφή της ενέργειας. |
| Μεσαία | Χρησιμοποιείται CommandDefinition.hotKey χωρίς αντίστοιχο υποστηριζόμενο μέλος του API. | Η ανάθεση δεν αποτελεί τεκμηριωμένη ρύθμιση συντόμευσης. |
| Μεσαία | Το package XML είχε μη έγκυρο χαρακτήρα &, placeholders GUID και ο installer περιελάμβανε προσωπικό session_config. | Μη έγκυρη συσκευασία ή διανομή τοπικών paths και state. |

Ο χαρακτηρισμός «κρίσιμη» αφορά την αξιοπιστία του backup. Δεν διαπιστώθηκε ότι
χάθηκαν ήδη αρχεία του χρήστη· διαπιστώθηκαν διαδρομές κώδικα που μπορούν να
παραλείψουν ή να παρουσιάσουν λανθασμένα την ολοκλήρωση ενός backup.

## Νέα αρχιτεκτονική

```text
ZenExport.py                private module loader, run/stop
    zenexport/addin.py      Fusion UI, events, main-thread adapter
    zenexport/config.py     IDs, version, profiles, validation
    zenexport/model.py      context identity, assembly snapshot
    zenexport/paths.py      safe names, unique allocation, version reservation
    zenexport/storage.py    per-user JSON, atomic writes, rotating logs
    zenexport/exporter.py   export plan, staging, outcomes, timings

tests/                      domain + simulated API regressions + packaging
 tools/build_bundle.py      deterministic bundle with explicit source allowlist
 tools/verify_fusion_api.py installed API member inspection
 .github/workflows/         automated Windows checks on push/PR
```

Μόνο το `addin.py` εισάγει `adsk`. Ο πυρήνας δοκιμάζεται εκτός Fusion.
Το entry point φορτώνει ιδιωτικό namespace, ώστε κοινά ονόματα όπως src/config
σε άλλα add-ins να μη συγκρούονται. Κάθε subscription ανήκει στο add-in instance
και αφαιρείται στο stop. Τα command-specific handlers απελευθερώνονται στο destroy.

Η ακύρωση native Save γίνεται αφού έχει ληφθεί έγκυρο Design και Document, πριν
ξεκινήσουν οι διάλογοι/εξαγωγές. Η 6.0.2 εκτελεί συγχρονισμένα από τον command
handler στο main thread, όπως ο αρχικός κώδικας. Δεν χρησιμοποιεί custom events,
ουρά ή worker threads. Ένας busy guard απορρίπτει επανείσοδο για το ίδιο έγγραφο,
ενώ αφήνει διαθέσιμο το native Save διαφορετικού εγγράφου. Document, geometry,
export και UI calls παραμένουν στο main thread.

Το context είναι UUID στα attributes, με συμπληρωματικό cloud DataFile ID.
Το όνομα εγγράφου και το revision ID χρησιμοποιούνται μόνο για τη μετάβαση από
παλιές καταχωρίσεις, όχι ως νέα μόνιμη ταυτότητα. Η εγγραφή attributes γίνεται πριν
το πρώτο F3D. Η 6.0.3 εισάγει τις παλιές αντιστοιχίσεις του session_config στο νέο
per-user config και συνεχίζει στον υπάρχοντα φάκελο όταν το ταίριασμα είναι μοναδικό.
Το παλιό session_config διατηρείται αμετάβλητο και δεν συσκευάζεται.

Τα components συγκρίνονται ως πραγματικά API entities μέσα σε buckets ID:
η Autodesk διευκρινίζει ότι linked copies/revisions μπορούν να έχουν ίδιο Component.id.
Τα bodies συγκρίνονται επίσης ως entities. Δεν συγκρίνονται strings entityToken ως
ταυτότητες, διότι η Autodesk αναφέρει ότι διαφορετικά tokens μπορούν να δείχνουν
στο ίδιο αντικείμενο. Τα ονόματα χρησιμοποιούνται μόνο για διαδρομές και περιορισμό
αναζήτησης, ποτέ ως τελική απόδειξη ταυτότητας.

Κάθε έκδοση περιέχει και τα Models της. Η δημιουργία του version directory γίνεται
με atomic mkdir και retry σε σύγκρουση. Κάθε αρχείο περνά από προσωρινό όνομα,
έλεγχο boolean αποτελέσματος και έλεγχο ύπαρξης/μη μηδενικού μεγέθους. Η επιτυχής
αντικατάσταση του προσωρινού αρχείου δεν αποτελεί σημασιολογικό έλεγχο της γεωμετρίας.
Η συνολική έκδοση δεν είναι μία συναλλαγή filesystem: πιθανή μερική αποτυχία
καταγράφεται και τα επιτυχημένα αρχεία παραμένουν διαθέσιμα.

Το export_manifest περιλαμβάνει κατάσταση, timings, μεγέθη και σφάλματα. Το append-only
export_events.jsonl καταγράφει σταδιακά τα αποτελέσματα χωρίς να ξαναγράφεται όλη η
αυξανόμενη αναφορά μετά από κάθε αρχείο. Διακοπή της διαδικασίας αφήνει in_progress,
χωρίς ψευδή σήμανση success. Last-success context ενημερώνεται μόνο όταν όλα τα
απαιτούμενα αρχεία έχουν επιτύχει. Το thumbnail είναι προαιρετικό.

## Απόδοση: τι αλλάζει και τι χρειάζεται μέτρηση

Το κόστος κυριαρχείται συνήθως από τους native translators και τη δημιουργία mesh.
Αυτό είναι υπόθεση προς επιβεβαίωση στα συγκεκριμένα projects, όχι αποτέλεσμα benchmark.

Για B μοναδικά ορατά BRep bodies, C μοναδικά non-root component targets και thumbnail,
ο αριθμός προγραμματισμένων αρχείων είναι:

| Προφίλ | Αρχεία/εργασίες | Χρήση |
| --- | --- | --- |
| full | 2 + B + 2C + 1 | Παράδοση όλων των formats και επιμέρους components |
| cad | 2 + 1 | F3D/STEP χωρίς per-part exports |
| backup | 1 + 1 | Συχνό παραμετρικό backup |

Παράδειγμα με B=200 και C=50: 303, 3 και 2 εργασίες αντίστοιχα.
Αυτό είναι αριθμητική του export plan, όχι αναλογία χρόνων. Οι native μετατροπές
έχουν διαφορετικό κόστος και η ορθότητα των F3D χρειάζεται επανεισαγωγή.

Οι ήδη υλοποιημένες αλλαγές μειώνουν τις διπλές εξαγωγές επαναλαμβανόμενων instances,
χρησιμοποιούν ένα snapshot αντί για ξεχωριστά περάσματα hash/export collection,
περιορίζουν το scanning εκδόσεων σε ένα αρχικό πέρασμα και προσφέρουν mesh quality
low/medium/high. Τα cad/backup παρακάμπτουν τη συλλογή bodies/occurrences, αφού δεν
ζητούν per-part αρχεία. Καταγράφεται χωριστά ο χρόνος snapshot. Η καταγραφή
αποτελεσμάτων αυξάνεται γραμμικά ως προς τα αρχεία.
Ο έλεγχος ορατότητας εξακολουθεί να διαβάζει proxies ανά ορατό instance· δεν
υποσχόμαστε κόστος ανεξάρτητο από τον αριθμό occurrences.

Το ασφαλές backup κάθε explicit save μπορεί να είναι ακριβότερο από το προηγούμενο
skip όταν εκείνο δεν δημιουργούσε αρχεία. Η επαναφορά incremental skipping χρειάζεται
πλήρη πολιτική invalidation, κάλυψη sketches/meshes/materials/references και αποδείξεις
με πραγματικά σχέδια. Η ασφάλεια δεν πρέπει να στηρίζεται μόνο σε έναν νέο hash.

## Προτεινόμενες επόμενες βελτιώσεις, κατά σειρά

1. **Live acceptance και recovery:** Έλεγχος πρώτου archive, δύο Untitled tabs,
   parameter edits, visibility/coordinates, linked assemblies, cancellation και reload.
   Reopen F3D/STEP και σύγκριση με το αρχικό σχέδιο.
2. **Μετρήσεις σε πραγματικά projects:** Μικρό part, μεσαίο assembly, μεγάλο assembly
   με repeated instances. Καταγραφή ανά format, median/p95 από αρκετές επαναλήψεις,
   έκδοσης Fusion, profile και mesh quality. Καμία δέσμευση επιτάχυνσης πριν από αυτό.
3. **Ανεξάρτητη επιλογή formats και απλό settings UI:** Τα profiles επαρκούν ως πρώτη
   υποδομή. Μετά τη μέτρηση, επιλογές component STEP/F3D χωριστά και ρητές STL units.
4. **Incremental παράγωγα με ασφαλές fallback:** Νέο F3D σε κάθε backup, επαναχρησιμοποίηση
   αμετάβλητων meshes/STEP μόνο όταν επαληθεύεται η ταυτότητα, γεωμετρία και πολιτική
   ορατότητας. Όχι background threading των Fusion API calls.
5. **Linked assemblies και πρόσθετοι τύποι:** Ρητή πολιτική πλήρους recovery F3D/F3Z,
   εξωτερικών dependencies, configurations, mesh bodies και ενδεχόμενου 3MF.
6. **Retention και διαγνωστικό UI:** Προβολή πλήρων/μερικών εκδόσεων και ελεγχόμενη
   διατήρηση ιστορικού αφού αποδειχθεί το recovery. Καμία αυτόματη διαγραφή τώρα.
7. **Παραγωγική διανομή:** Build/sign MSI και smoke test σε καθαρό περιβάλλον.
   Το υπάρχον WiX v3 scaffold διορθώθηκε αλλά δεν έγινε compile/install.

## Όρια της υποδομής

Atomic JSON replacement προστατεύει από κομμένη εγγραφή, όχι από last-writer-wins
μεταξύ ανεξάρτητων Fusion processes. Χρησιμοποιήστε χωριστό ZENEXPORT_DATA_DIR αν
τρέχουν ταυτόχρονα ανεξάρτητα instances. Τα version directories προστατεύονται από
ταυτόχρονη δέσμευση, αλλά δεν είναι εγγύηση durability σε κάθε network filesystem.
Δεν υπάρχει ακόμη GUI settings ή αυτόματη πολιτική retention. Το local export δεν
αποτελεί native document save και μπορεί να παραμένει το modified flag του Fusion.

## Ιστορικό 6.0.1: ανεπιτυχής αλλαγή αποστολής αιτήματος

Η πρώτη αναφορά πραγματικής εκτέλεσης έδειξε ότι το add-in ξεκίνησε, αλλά η κλήση
fireCustomEvent μέσα από commandStarting δεν επέστρεψε θετική αποδοχή. Το αρχικό
log δεν διακρίνει False από None ούτε αποδεικνύει τον εσωτερικό λόγο απόρριψης.
Το σφάλμα εμφανίστηκε πριν ξεκινήσει export· το native Save δεν είχε ακυρωθεί.

Η 6.0.1 δοκίμασε τη διαδρομή worker προς main thread που τεκμηριώνει η Autodesk.
Ο worker καλούσε μόνο fireCustomEvent με ρητό payload. Ο κύριος handler περίμενε έως
0,5 δευτερόλεπτα για αποδοχή, χωρίς να περιμένει την ίδια την εξαγωγή. Αποτυχία,
exception ή timeout αφήνουν διαθέσιμο το native Save. Ένα μοναδικό token ανά αίτημα
απορρίπτει καθυστερημένες ειδοποιήσεις μετά από timeout ή reload. Τα μηνύματα σφάλματος
περιλαμβάνουν πλέον την αιτία και η επιστρεφόμενη τιμή καταγράφεται σε περίπτωση απόρριψης.

Η επόμενη πραγματική δοκιμή επέστρεψε result=False και από τον worker. Επομένως η
υπόθεση ότι έφταιγε μόνο το νήμα κλήσης δεν επιβεβαιώθηκε και η 6.0.1 δεν έλυσε το
πρόβλημα. Οι προσομοιώσεις της δεν κάλυπταν τη μόνιμη απόρριψη που παρατηρήθηκε.

## Διόρθωση 6.0.2: επαναφορά άμεσης εκτέλεσης

Αφαιρέθηκε πλήρως η εξάρτηση από register/fire/unregisterCustomEvent και από τον
worker. Η άμεση εκτέλεση διατηρεί την αρχική διαδρομή κλήσης, μαζί με τον νέο
ελεγχόμενο exporter. Τα tests προσομοιώνουν πλέον register που επιτυγχάνει και
fire που επιστρέφει πάντα False: η εξαγωγή πρέπει να ολοκληρώνεται χωρίς να καλεί
κανένα από αυτά. Καλύπτονται toolbar, native Save, ακύρωση πριν τη μετατροπή,
επανείσοδος του ίδιου εγγράφου, Save άλλου εγγράφου, exception και reload.
Σχέδια με απουσία userParameters collection αντιμετωπίζονται επίσης ως κενά.

Αυτή η αλλαγή παρακάμπτει το συγκεκριμένο σημείο αποτυχίας. Δεν αποδεικνύει την
εσωτερική αιτία του False στο Fusion ούτε την ορθότητα των native translators.
Απαιτείται Stop/Run και επανάληψη μέσα στο Fusion για επιβεβαίωση πραγματικού export.

## Διόρθωση 6.0.3: ανάκτηση παλιών προορισμών

Η 6.0.3 διορθώνει επιπλέον την παράλειψη migration: το πραγματικό παλιό config είχε
254 καταχωρίσεις, με 17 υφιστάμενους φακέλους project, ενώ το νέο config δεν είχε
context entries. Ο έλεγχος αναγνώρισης χρησιμοποιεί το πραγματικό patterns_v01.
Τα legacy records αντιγράφονται χωρίς τα παλιά hashes, ώστε να μην εισαχθεί ψευδές
last-success state. Πολλαπλές καταχωρίσεις του ίδιου φακέλου συνενώνονται, απούσα
διαδρομή δεν δημιουργεί νέο project, και αμφίσημα διαφορετικά projects επιλέγονται
από λίστα υπαρχόντων φακέλων. Τα test fixtures επιβεβαιώνουν συνέχεια v04 → v05,
διατήρηση του προηγούμενου archive και επαναφόρτωση μετά τη μετάβαση.

## Έκδοση 6.1.0: οργάνωση αρχείων και ονόματα revision

Οι νέες εκδόσεις αποθηκεύονται στο Revisions/vNN_περιγραφή, με CAD για όλα τα F3D/STEP
(και των components), Models για τα STL, και _Info για preview/manifest/events.
Η αρίθμηση διαβάζει και το παλιό CAD/vNN ιστορικό. Τα παλιά snapshots δεν μετακινούνται.
Πριν δεσμευτεί έκδοση προσφέρεται προαιρετική περιγραφή. Κενό σημαίνει αριθμητική
έκδοση, ενώ Cancel σταματά χωρίς νέα αρχεία ή αλλαγή attributes. Η περιγραφή του
φακέλου καθαρίζεται/περιορίζεται και το πλήρες κείμενο αποθηκεύεται στο manifest.
Το schema του manifest γίνεται 2· το schema του per-user config παραμένει 1.

Η αριθμητική ταυτότητα vNN παραμένει σταθερή ανεξάρτητα από την περιγραφή. Μικρά
reservation files στο Revisions/_Info/version_reservations δεσμεύουν ατομικά τον
αριθμό, ώστε ταυτόχρονες περιγραφές να μην δημιουργούν δύο διαφορετικά vNN.
Ο έλεγχος καλύπτει ανάμεικτο παλιό/νέο ιστορικό, ελληνικά, ασφάλεια διαδρομών,
ταυτόχρονα ονόματα, οργάνωση όλων των formats και σωστό last-success manifest path.
Η νέα προτίμηση prompt_revision_name επιτρέπει απενεργοποίηση του διαλόγου.
Η συγκεκριμένη νέα ροή δεν έχει ακόμη επιβεβαιωθεί μέσα στο Fusion.

## Έκδοση 6.1.1: διόρθωση της διάταξης μετά τη διευκρίνιση χρήστη

Η τελική ζητούμενη δομή είναι CAD/vNN_περιγραφή για F3D/STEP και
Models/vNN_περιγραφή για τα αντίστοιχα STL. Οι αναφορές/εικόνες χρησιμοποιούν
_Info/vNN_περιγραφή. Δεν δημιουργείται νέος γονικός φάκελος Revisions. Το manifest
schema γίνεται 3, με paths σχετικά προς το project και ρητή καταγραφή των τριών
αντίστοιχων διαδρομών. Το παράθυρο φακέλου ανοίγει στη ρίζα του project.

Το layout.py μεταφέρει παλιές κοινές εκδόσεις και ενσωματωμένα Models στους σωστούς
φακέλους. Ελέγχει διαδρομές και συγκρούσεις πριν την πρώτη μεταφορά, αποθηκεύει
αντίγραφα των αρχικών αναφορών, και καταγράφει εκκρεμείς ενημερώσεις σε journal.
Τα native αρχεία δεν ξαναγράφονται. Σε fallback αντιγραφής ελέγχεται SHA-256 πριν
αφαιρεθεί η πηγή. Αφαιρούνται αποκλειστικά άδειοι παλιοί φάκελοι. Παλιές εξαγωγές
χωρίς ιστορική αντιστοίχιση κρατούνται ως _Legacy_unversioned.

Έγινε πραγματική μεταφορά στο patterns: 25 αρχεία άλλαξαν διαδρομή, 24 αρχεία
CAD/STL/PNG επιβεβαιώθηκαν byte-identical και το last-success manifest διορθώθηκε.
Η ρίζα περιέχει πλέον μόνο CAD, Models και _Info. Το v04_new test υπάρχει με ίδιο
όνομα και στους δύο φακέλους. Πριν τη μεταφορά κρατήθηκε πλήρες ZIP στο τοπικό
.git/patterns-before-layout-6.1.1.zip και αντίγραφο του per-user config.
Οι δοκιμές καλύπτουν και διακοπή μετά τη μεταφορά payloads, σύγκρουση περιεχομένου,
μη ασφαλή report paths και επανάληψη χωρίς διπλή μεταφορά. Το επόμενο save από
τη νέα έκδοση μέσα στο Fusion παραμένει προς επιβεβαίωση.

## Πηγές API

- [Component.revisionId](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Component_revisionId.htm): μεταβολή του revision όταν αλλάζει το component.
- [Component.id](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Component_id.htm): όρια μοναδικότητας σε assemblies με linked αντίγραφα/revisions.
- [BRepBody.entityToken](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_BRepBody_entityToken.htm): αποφυγή σύγκρισης token strings ως ταυτότητας.
- [Application.fireCustomEvent](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application_fireCustomEvent.htm): queued εκτέλεση στο main thread όταν το Fusion είναι idle.
- [ExportManager.execute](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_execute.htm): το αποτέλεσμα είναι boolean επιτυχίας.
- [CommandDefinition](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_CommandDefinition.htm): υποστηριζόμενα μέλη της command definition.

Η προϋπάρχουσα έκδοση του ZenExport.py, μαζί με τις μη committed αλλαγές της,
διατηρήθηκε τοπικά στο .git/ZenExport.pre-infrastructure.py για σύγκριση/ανάκτηση.
