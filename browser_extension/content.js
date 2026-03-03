// Skrypt wstrzykiwany na każdą stronę z otwartym pojedynczym raportem 
if (window.location.href.includes("screen=report") && window.location.href.includes("view=")) {
    // Ekstrakcja ID raportu
    let reportIdMatch = window.location.href.match(/view=(\d+)/);

    if (reportIdMatch && reportIdMatch[1]) {
        let currentReportId = reportIdMatch[1];
        let reportRawHTML = document.documentElement.outerHTML;

        // Powiadom konsolę
        console.log(`[TWB-Ext] Natrafiono na raport ${currentReportId}. Wysyłanie do gniazda bota...`);

        // Wypchnięcie surowego HTML-a do gniazda Python (Bota)
        fetch("http://127.0.0.1:5000/api/plugin_report", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                "report_id": currentReportId,
                "html": reportRawHTML
            })
        })
            .then(response => response.json())
            .then(data => {
                if (data.ok) {
                    console.log(`[TWB-Ext] BOT ZAAKCEPTOWAŁ: ${data.message}`);
                } else {
                    console.warn(`[TWB-Ext] ODRZUCENIE BOTA: ${data.message}`);
                }
            })
            .catch(error => {
                console.error("[TWB-Ext] Brak połączenia z serwerem bota", error);
            });
    }
}
