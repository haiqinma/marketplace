import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const skillsDir = path.join(root, "skills");
const toolServersDir = path.join(root, "tools", "servers");
const languages = ["cn", "en"];

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJson(file, data) {
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function isLocalizedText(value) {
  if (typeof value === "string") return value.length > 0;
  return Boolean(
    value &&
      typeof value === "object" &&
      (typeof value.cn === "string" || typeof value.en === "string"),
  );
}

function validateSkill(skill, file) {
  assert(skill.schemaVersion === "1.0", `${file}: schemaVersion must be 1.0`);
  assert(
    typeof skill.id === "string" && /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(skill.id),
    `${file}: id must be kebab-case`,
  );
  assert(typeof skill.version === "string", `${file}: version is required`);
  assert(isLocalizedText(skill.name), `${file}: name is required`);
  assert(skill.launch?.type, `${file}: launch.type is required`);
  assert(skill.instructions?.type, `${file}: instructions.type is required`);
  assert(skill.release?.status !== "removed", `${file}: removed skills should not be committed`);
}

function validateAgentSkill(skillFolder) {
  const file = path.join(skillsDir, skillFolder, "SKILL.md");
  const relative = path.relative(root, file);
  const content = fs.readFileSync(file, "utf8");
  const frontmatter = content.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  assert(frontmatter, `${relative}: SKILL.md must start with YAML frontmatter`);
  const rawName = frontmatter[1].match(/^name:\s*(.+?)\s*$/m)?.[1];
  const name = rawName?.match(/^(['"])(.*)\1$/)?.[2] ?? rawName;
  assert(name && !name.includes(" ") && !name.includes("#"), `${relative}: frontmatter name is required`);
  assert(name === skillFolder, `${relative}: skill name must match parent folder ${skillFolder}`);
}

function validateSkillReadme(skillFolder) {
  const file = path.join(skillsDir, skillFolder, "README.md");
  const relative = path.relative(root, file);
  assert(
    fs.existsSync(file),
    `${relative}: every skill must provide a bilingual README.md`,
  );

  const content = fs.readFileSync(file, "utf8");
  assert(
    /^#\s+\S.+$/m.test(content),
    `${relative}: README.md must contain a level-one title`,
  );
  const bilingual = content.match(
    /^## 中文\s*\r?\n([\s\S]*?)^## English\s*\r?\n([\s\S]+)$/m,
  );
  assert(
    bilingual,
    `${relative}: README.md must contain ## 中文 and ## English sections`,
  );

  const chinese = bilingual[1].trim();
  const english = bilingual[2].trim();
  assert(
    chinese && /[\u3400-\u9fff]/u.test(chinese),
    `${relative}: 中文 section must contain Chinese content`,
  );
  assert(
    english && /[A-Za-z]{3}/.test(english),
    `${relative}: English section must contain English content`,
  );
}

function validateToolServer(server, file) {
  assert(server.schemaVersion === "1.0", `${file}: schemaVersion must be 1.0`);
  assert(
    typeof server.id === "string" && /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(server.id),
    `${file}: id must be kebab-case`,
  );
  assert(typeof server.version === "string", `${file}: version is required`);
  assert(isLocalizedText(server.name), `${file}: name is required`);
  assert(
    isLocalizedText(server.description),
    `${file}: description is required`,
  );
  assert(typeof server.repo === "string" && server.repo, `${file}: repo is required`);
  assert(Array.isArray(server.tags), `${file}: tags must be an array`);
  assert(typeof server.command === "string" && server.command, `${file}: command is required`);
  assert(Array.isArray(server.baseArgs), `${file}: baseArgs must be an array`);
  assert(typeof server.configurable === "boolean", `${file}: configurable must be a boolean`);
  if (server.runtimes !== undefined) {
    assert(
      Array.isArray(server.runtimes) &&
        server.runtimes.length > 0 &&
        server.runtimes.every((runtime) => ["standalone", "desktop"].includes(runtime)),
      `${file}: runtimes must contain standalone and/or desktop`,
    );
  }
  if (server.platforms !== undefined) {
    assert(
      Array.isArray(server.platforms) &&
        server.platforms.length > 0 &&
        server.platforms.every((platform) => ["macos", "windows", "linux"].includes(platform)),
      `${file}: platforms must contain supported platform ids`,
    );
  }
  if (server.permissions !== undefined) {
    assert(
      Array.isArray(server.permissions) &&
        server.permissions.every(
          (permission) =>
            typeof permission?.id === "string" &&
            permission.id.length > 0 &&
            isLocalizedText(permission.description),
        ),
      `${file}: permissions must declare an id and localized description`,
    );
  }
  if (server.requirements !== undefined) {
    assert(
      Array.isArray(server.requirements) && server.requirements.every(isLocalizedText),
      `${file}: requirements must be localized text entries`,
    );
  }
  if (server.configSchema?.properties) {
    Object.entries(server.configSchema.properties).forEach(([key, property]) => {
      if (property && property.sensitive !== undefined) {
        assert(
          typeof property.sensitive === "boolean",
          `${file}: configSchema.properties.${key}.sensitive must be boolean`,
        );
      }
    });
  }
  assert(server.release?.status !== "removed", `${file}: removed tool servers should not be committed`);
}

function collectSkills() {
  const grouped = {};
  const skillIndex = [];
  const seen = new Set();
  let agentSkillCount = 0;

  for (const lang of languages) {
    grouped[lang] = [];
  }

  if (!fs.existsSync(skillsDir)) {
    return {
      skillIndex,
      grouped,
      agentSkillCount,
    };
  }

  const skillFolders = fs
    .readdirSync(skillsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  for (const skillFolder of skillFolders) {
    assert(
      /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(skillFolder),
      `skills/${skillFolder}: folder must be kebab-case`,
    );

    const skillDir = path.join(skillsDir, skillFolder);
    const chatLanguages = languages.filter((lang) => fs.existsSync(path.join(skillDir, `${lang}.json`)));
    const hasAgentSkill = fs.existsSync(path.join(skillDir, "SKILL.md"));
    assert(
      chatLanguages.length > 0 || hasAgentSkill,
      `skills/${skillFolder}: expected cn.json, en.json, or SKILL.md`,
    );
    validateSkillReadme(skillFolder);

    if (hasAgentSkill) {
      validateAgentSkill(skillFolder);
      agentSkillCount += 1;
    }

    for (const lang of languages) {
      const absolute = path.join(skillDir, `${lang}.json`);
      if (!fs.existsSync(absolute)) continue;
      const relative = path.relative(root, absolute);
      const skill = readJson(absolute);
      validateSkill(skill, relative);

      assert(
        skill.id === skillFolder,
        `${relative}: skill id must match parent folder ${skillFolder}`,
      );

      const key = `${lang}:${skill.id}`;
      assert(!seen.has(key), `${relative}: duplicate skill id ${skill.id}`);
      seen.add(key);

      grouped[lang].push(skill);
      skillIndex.push({
        id: skill.id,
        lang,
        version: skill.version,
        name: skill.name,
        description: skill.description,
        category: skill.category,
        tags: skill.tags ?? [],
        path: relative,
        release: skill.release,
      });
    }
  }

  return {
    skillIndex,
    grouped,
    agentSkillCount,
  };
}

function collectToolServers() {
  const servers = [];
  const index = [];
  const seen = new Set();

  if (!fs.existsSync(toolServersDir)) {
    return { servers, index };
  }

  const files = fs
    .readdirSync(toolServersDir)
    .filter((file) => file.endsWith(".json"))
    .sort();

  for (const file of files) {
    const absolute = path.join(toolServersDir, file);
    const relative = path.relative(root, absolute);
    const server = readJson(absolute);
    validateToolServer(server, relative);

    assert(!seen.has(server.id), `${relative}: duplicate tool server id ${server.id}`);
    seen.add(server.id);

    servers.push(server);
    index.push({
      id: server.id,
      version: server.version,
      name: server.name,
      description: server.description,
      tags: server.tags ?? [],
      path: relative,
      release: server.release,
    });
  }

  return { servers, index };
}

const { skillIndex, grouped, agentSkillCount } = collectSkills();
const { servers: toolServers, index: toolIndex } = collectToolServers();

writeJson(path.join(root, "index.json"), skillIndex);
writeJson(path.join(root, "packages.json"), grouped);
writeJson(path.join(root, "tools", "index.json"), toolIndex);
writeJson(path.join(root, "tools", "packages.json"), toolServers);

console.log(`Built ${skillIndex.length} Chat skill packages`);
console.log(`Validated ${agentSkillCount} Agent skills`);
console.log(`Built ${toolIndex.length} tool packages`);
