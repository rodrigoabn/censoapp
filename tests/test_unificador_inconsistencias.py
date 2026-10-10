from __future__ import annotations

import io
import zipfile

import openpyxl
import pytest

from apps.unificador_inconsistencias.src.processor import (
    SHEETS,
    build_school_reports_zip,
    read_active_schools,
)
from apps.unificador_inconsistencias.src.statistics_pdf import build_statistics_pdf


def _xlsx_bytes(sheet_name: str, rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    for row in rows:
        worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_zip_has_one_five_sheet_workbook_per_active_school():
    schools = _xlsx_bytes(
        "Escolas",
        [
            ["Código INEP", "Nome da Unidade"],
            ["33000001", "Escola Um"],
            ["33000002", "Escola Dois"],
        ],
    )
    units = _xlsx_bytes(
        "Unidades",
        [
            ["Código do Inep", "Unidade Escolar", "Aba", "Detalhes"],
            ["33000001", "Escola Um", "Identificação", "Campo obrigatório vazio"],
            ["33000001", "Escola Um", "Endereço", "Código de município inválido"],
            ["33000099", "Escola externa", "Identificação", "Não deve ser incluída"],
        ],
    )
    gestor = _xlsx_bytes(
        "Gestores",
        [["Código do Inep", "Unidade Escolar", "Aba", "Detalhes"]],
    )

    archive_bytes, stats = build_school_reports_zip(
        schools,
        {"unidades": units, "gestores": gestor},
        {"turmas", "alunos", "professores"},
    )

    assert stats["total_units"] == 2
    assert stats["units_with_inconsistencies"] == 1
    assert stats["units_without_inconsistencies"] == 1
    assert stats["by_type"]["unidades"] == {
        "label": "Cadastro da Unidade",
        "used": True,
        "units": 1,
        "issues": 2,
    }
    assert stats["by_type"]["turmas"]["used"] is False
    assert stats["per_school"][0]["total_issues"] == 2
    assert stats["per_school"][1]["total_issues"] == 0

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == [
            "Escola Um.xlsx",
            "Escola Dois(SEM INCONSISTENCIAS).xlsx",
        ]
        first = openpyxl.load_workbook(io.BytesIO(archive.read(archive.namelist()[0])))
        second = openpyxl.load_workbook(io.BytesIO(archive.read(archive.namelist()[1])))

    assert first.sheetnames == ["Cadastro da Unidade", "Turmas", "Alunos", "Professores"]
    assert first["Cadastro da Unidade"].cell(2, 4).value == "Campo obrigatório vazio"
    assert "Unidade não possui inconsistência" not in [
        cell.value
        for worksheet in first.worksheets
        for row in worksheet.iter_rows()
        for cell in row
    ]
    assert all(
        first[sheet].cell(1, 1).value == "Relatório não gerado"
        for sheet in ("Turmas", "Alunos", "Professores")
    )
    assert second.sheetnames == list(SHEETS.values())
    assert second["Cadastro da Unidade"]["A1"].value == "Unidade não possui inconsistência"
    assert second["Gestores"]["A1"].value == "Unidade não possui inconsistência"
    assert all(
        second[sheet].cell(1, 1).value == "Relatório não gerado"
        for sheet in ("Turmas", "Alunos", "Professores")
    )

    pdf = build_statistics_pdf(stats)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_school_codes_must_be_eight_digits_starting_with_33():
    schools = _xlsx_bytes(
        "Escolas",
        [["Código INEP", "Nome"], ["32000001", "Escola inválida"]],
    )

    with pytest.raises(ValueError, match="8 dígitos e iniciar com 33"):
        read_active_schools(schools)


def test_school_codes_must_be_unique():
    schools = _xlsx_bytes(
        "Escolas",
        [
            ["Código INEP", "Nome"],
            ["33000001", "Escola Um"],
            ["33000001", "Escola Duplicada"],
        ],
    )

    with pytest.raises(ValueError, match="duplicado"):
        read_active_schools(schools)


def test_duplicate_school_names_are_rejected_as_output_filenames():
    schools = _xlsx_bytes(
        "Escolas",
        [
            ["Código INEP", "Nome"],
            ["33000001", "Escola Um"],
            ["33000002", "Escola Um"],
        ],
    )

    with pytest.raises(ValueError, match="nomes de unidades escolares repetidos"):
        build_school_reports_zip(
            schools,
            {},
            {"unidades", "gestores", "turmas", "alunos", "professores"},
        )


def test_missing_report_requires_upload_or_ignore():
    schools = _xlsx_bytes("Escolas", [["INEP", "Unidade"], ["33000001", "Escola Um"]])

    with pytest.raises(ValueError, match="Envie o relatório"):
        build_school_reports_zip(schools, {}, set())


def test_report_requires_inep_column():
    schools = _xlsx_bytes("Escolas", [["INEP", "Unidade"], ["33000001", "Escola Um"]])
    report = _xlsx_bytes("Relatório", [["Unidade Escolar", "Detalhes"], ["Escola Um", "Erro"]])

    with pytest.raises(ValueError, match="coluna de código INEP"):
        build_school_reports_zip(
            schools,
            {"unidades": report},
            {"gestores", "turmas", "alunos", "professores"},
        )


def test_report_text_is_written_as_text_not_as_formula():
    schools = _xlsx_bytes("Escolas", [["INEP", "Unidade"], ["33000001", "Escola Um"]])
    report = _xlsx_bytes(
        "Relatório",
        [["Código do Inep", "Detalhes"], ["33000001", "=1+1"]],
    )
    source_workbook = openpyxl.load_workbook(io.BytesIO(report))
    source_workbook["Relatório"]["B2"].data_type = "s"
    source_buffer = io.BytesIO()
    source_workbook.save(source_buffer)

    archive_bytes, _ = build_school_reports_zip(
        schools,
        {"unidades": source_buffer.getvalue()},
        {"gestores", "turmas", "alunos", "professores"},
    )

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        workbook = openpyxl.load_workbook(io.BytesIO(archive.read(archive.namelist()[0])))
    cell = workbook["Cadastro da Unidade"]["B2"]
    assert cell.value == "'=1+1"
    assert cell.data_type == "s"
