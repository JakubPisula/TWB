// Skrypt wstrzykiwany na każdą stronę z otwartym pojedynczym raportem 
if (window.location.href.includes("screen=report") && window.location.href.includes("view=")) {
    // Ekstrakcja ID raportu
    let reportIdMatch = window.location.href.match(/view=(\d+)/);

    if (reportIdMatch && reportIdMatch[1]) {
        let currentReportId = reportIdMatch[1];
        let reportRawHTML = document.documentElement.outerHTML;

        // Powiadom konsolę
        console.log(`[TWB-Ext] Natrafiono na raport ${currentReportId}. Wysyłanie do background bota...`);

        chrome.runtime.sendMessage({
            action: 'send_report',
            data: {
                "report_id": currentReportId,
                "html": reportRawHTML
            }
        }, response => {
            if (response && response.ok) {
                console.log(`[TWB-Ext] BOT ZAAKCEPTOWAŁ: ${response.message}`);
            } else {
                console.warn(`[TWB-Ext] ODRZUCENIE LUB BŁĄD BOTA: ${response ? response.message : 'No response'}`);
            }
        });
    }
}
