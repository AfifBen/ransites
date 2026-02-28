function showToast(message, type = 'success') {
    const toastElement = document.getElementById('liveToast');
    const toastBody = document.getElementById('toastMessage');

    if (!toastElement || !toastBody) return;

    toastElement.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-info');
    toastElement.classList.add('bg-' + (type === 'error' ? 'danger' : type));

    toastBody.textContent = message;

    const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
    toast.show();
}

function debounce(fn, wait) {
    let timer;
    return function () {
        const args = arguments;
        clearTimeout(timer);
        timer = setTimeout(function () {
            fn.apply(null, args);
        }, wait);
    };
}

function initializeDataTable(tableId, scrollX, languageUrl) {
    const selector = '#' + tableId;
    const $table = $(selector);

    if (!$table.length) return null;

    if ($.fn.DataTable.isDataTable(selector)) {
        $table.DataTable().destroy();
    }

    $table.addClass('datatable-pending').removeClass('datatable-ready');

    const isScrollX = (scrollX === 'True' || scrollX === 'true' || scrollX === true);
    const isSitesTable = tableId === 'sitesTable';
    const isCellsTable = tableId === 'cellsTable';
    const pageParams = new URLSearchParams(window.location.search || '');
    const dqFilter = pageParams.get('dq_filter') || '';
    const defaultOrder = (isSitesTable || isCellsTable) ? [[2, 'asc']] : [[1, 'asc']];
    const columnDefs = [
        {
            targets: 0,
            orderable: false,
            className: 'text-center',
            render: function () {
                return '<input type="checkbox" class="form-check-input row-checkbox">';
            }
        }
    ];

    // Keep ID column for internal actions, but hide it on Sites table UI.
    if (isSitesTable) {
        columnDefs.push({
            targets: 1,
            visible: false,
            searchable: false
        });
    }

    const table = $table.DataTable({
        pageLength: isCellsTable ? 50 : 10,
        lengthMenu: isCellsTable ? [10, 25, 50, 100] : [5, 10, 20, 50],
        order: defaultOrder,
        processing: isCellsTable,
        serverSide: isCellsTable,
        ajax: isCellsTable ? {
            url: '/cells/data',
            type: 'GET',
            data: function (d) {
                if (dqFilter) d.dq_filter = dqFilter;
            }
        } : undefined,
        select: {
            style: 'multi',
            selector: 'td:first-child'
        },
        columnDefs: columnDefs,
        scrollX: isScrollX,
        scrollY: '55vh',
        scrollCollapse: true,
        autoWidth: false,
        deferRender: true,
        dom: "<'row mb-3'<'col-sm-12 col-md-6'l><'col-sm-12 col-md-6'f>>" +
             "<'row'<'col-sm-12'tr>>" +
             "<'row mt-3'<'col-sm-12 col-md-5'i><'col-sm-12 col-md-7'p>>",
        language: {
            search: 'Search:',
            lengthMenu: 'Show _MENU_ entries',
            info: 'Showing _START_ to _END_ of _TOTAL_ entries',
            infoEmpty: 'No data available',
            zeroRecords: 'No matching records found',
            processing: 'Loading cells...',
            select: {
                rows: {
                    _: '%d rows selected',
                    0: '',
                    1: '1 row selected'
                }
            }
        },
        initComplete: function () {
            const api = this.api();

            const finalizeLayout = function () {
                api.columns.adjust().draw(false);
                const $wrapper = $table.closest('.dataTables_wrapper');
                $wrapper.find('table').removeClass('datatable-pending').addClass('datatable-ready');
                $table.removeClass('datatable-pending').addClass('datatable-ready');
            };

            requestAnimationFrame(finalizeLayout);
            setTimeout(finalizeLayout, 80);
            setTimeout(finalizeLayout, 220);
        }
    });

    function updateActionButtons() {
        const selectedRows = table.rows({ selected: true });
        const count = selectedRows.count();

        const deleteBtn = $('#deleteBulkBtn');
        const editBtn = $('#editBtn');
        const siteProfileBtn = $('#siteProfileBtn');
        const countSpan = $('#selectCount');
        const isSiteTable = tableId === 'sitesTable';

        if (count > 0) {
            if (countSpan.length) countSpan.text(count);
            deleteBtn.fadeIn(120);
        } else {
            deleteBtn.fadeOut(120);
            $('#selectAll').prop('checked', false);
        }

        if (count === 1) {
            const rowData = selectedRows.data()[0];
            const cleanId = $($.parseHTML(rowData[1])).text() || rowData[1];

            editBtn.attr('data-id', cleanId);
            editBtn.fadeIn(120);
            if (isSiteTable && siteProfileBtn.length) {
                siteProfileBtn.attr('data-id', cleanId).fadeIn(120);
            }
        } else {
            editBtn.fadeOut(120);
            editBtn.removeAttr('data-id');
            if (siteProfileBtn.length) {
                siteProfileBtn.fadeOut(120);
                siteProfileBtn.removeAttr('data-id');
            }
        }
    }

    $('#selectAll').off('click').on('click', function () {
        if (this.checked) {
            const rowsScope = isCellsTable ? { page: 'current' } : { search: 'applied' };
            table.rows(rowsScope).select();
        } else {
            table.rows().deselect();
        }
    });

    table.on('select deselect', function () {
        updateActionButtons();

        table.rows().every(function () {
            $(this.node()).find('.row-checkbox').prop('checked', this.selected());
        });

        if (table.rows({ selected: true }).count() < table.rows({ search: 'applied' }).count()) {
            $('#selectAll').prop('checked', false);
        }
    });

    const adjust = debounce(function () {
        table.columns.adjust().draw(false);
    }, 80);

    $(window).off('resize.' + tableId).on('resize.' + tableId, adjust);
    $(window).off('load.' + tableId).on('load.' + tableId, adjust);

    $(document)
        .off('shown.bs.collapse.dt.' + tableId)
        .on('shown.bs.collapse.dt.' + tableId, adjust)
        .off('shown.bs.tab.dt.' + tableId)
        .on('shown.bs.tab.dt.' + tableId, adjust)
        .off('shown.bs.modal.dt.' + tableId)
        .on('shown.bs.modal.dt.' + tableId, adjust);

    return table;
}
