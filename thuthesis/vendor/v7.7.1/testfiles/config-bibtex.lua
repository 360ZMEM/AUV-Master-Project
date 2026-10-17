checksuppfiles = { "*.tex", "*.bib" }
testfiledir = "testfiles/10-bibtex"

includetests = { "*" }
excludetests = {}

checkruns = 3

function runtest_tasks(name, run)
  if run == 1 then
    local aux_files = filelist(testdir, name .. "*.aux")
    local commands = {}
    for _, aux_file in ipairs(aux_files) do
      local base_name = jobname(aux_file)
      table.insert(commands, "bibtex -terse " .. base_name)
    end
    local command = table.concat(commands, os_concat)
    -- io.stderr:write(command .. "\n")
    return command
  else
    return ""
  end
end
